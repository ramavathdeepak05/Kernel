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

## Current status (2026-06-15)

**All 14 governance layers + the delivery phase are built and green, an operator console ships
alongside, and the commercial productization program (3-tier packaging) is complete — waves 0–1 are
landed, the WS-C/D/E/F/G workstreams are in, and the final Wave-2 slice (console OIDC login +
per-tier UI gating) is done, and the WS-C billing edge is now **end-to-end and
turnkey** (config/env-driven adapters → outbound checkout → provider → inbound webhook → tier flip,
with a console upgrade page). Suite: 861 tests passing, 10 skipped on a bare checkout — and 871
passing / 0 skipped once the real external deps are live (the 10 skips are the Postgres + OpenBao
integration tests, validated against a GCP Cloud SQL instance and a Dockerized OpenBao; see the
Log).** Ten feature waves have landed on top of the core kernel since the Wave-2
milestone below: (1) full layer completion + delivery, (2) a security-hardening + composable-governance
pass, (3) a decision-only authorize/monitor surface + reference PEP, (4) a zero-friction integration
layer, (5) config-wiring the CEL policy engine + a durable (Postgres) policy store, (6) the Policy
Management HTTP API (`/v1/policies`) with route-level control-plane authz, (7) the
backtest→ImpactReport simulate bridge + dashboard read-model query routes, (8) the operator console
(React/Vite web UI) + HITL approvals API + CORS, (9) **commercial tiering** — an entitlement/tier
engine, an offline-licensed Enterprise path, self-serve account provisioning, and a shared
multi-tenant SaaS plane that routes each request to its tier's kernel, and (10) the **WS-D
auth/metering edge** — API-key authentication, fine-grained RBAC scopes, per-tier rate limiting, and
request-logging/correlation-id middleware. See the Log for the per-wave detail. Extension decisions are
recorded as ADR-0002…0011 (`docs/adr/`).

The kernel now exposes four ways in — REST API (`/v1/actions`, `/v1/authorize`, `/v1/inference`,
`/v1/ledger`, `/v1/policies`, `/v1/dashboard`, `/v1/approvals`, plus `/v1/signup` + `/v1/admin/*`),
the Python SDK (`@kernel.guard` / `kernel.wrap` / `kernel.proxy` / `kernel.check` / `kernel.generate`
/ `for_agent`), a reference enforcement-point middleware, and the **operator console** (`console/` —
a plain React/Vite app over the REST API) — all running over one composable `GovernanceProfile` model
with per-agent identity, served either as a single dedicated kernel or via the new
`TieredKernelProvider` shared plane.

### Next planned work — productization program (3 tiers from one codebase)
Per the go-live plan, the work is sequenced in waves. **Wave 0 (entitlement/tiering foundation),
Wave 1 (shared-plane API routing + self-serve provisioning), and the core of WS-D (API-key auth +
RBAC scopes + per-tier rate limiting + request logging, ADR-0011) are done.** **Named IdP connectors**
(Okta/Auth0/Keycloak via OIDC discovery + JWKS rotation, layered on `JWTIdentityAdapter`) are
**done**, and the final WS-D/Wave-2 slice — **console OIDC login (Authorization Code + PKCE) +
per-tier UI gating** over a new `GET /v1/me/entitlements` — is now **done** too (see the top Log
entry).
**WS-C** (Stripe + Razorpay billing → tier flips; usage metering on the access log) is now **done**
(see the top Log entry). **WS-F** (regulator ledger-proof export), **WS-G** (GDPR crypto-shredding
erasure), and **WS-E** (Enterprise isolation hardening — schema-per-tenant + RLS) are now **done**
too — the productization workstreams WS-C/D/E/F/G are all landed. What remains are the pre-sale
blockers that are **not pure code** (and were always tracked separately): the **K·02 external
cryptographic review** (a third-party engagement) and **policy content packs** (the actual RBI / EU AI
Act / DPDP rule sets — a regulatory-authoring effort the kernel *enforces* but does not itself write).
With the console OIDC slice landed, **all planned code is complete**: the kernel engine, all 14
governance layers, delivery surfaces (incl. the operator console with OIDC login + tier gating), and
the full commercial/productization program are code-complete and green. The only remaining items are
the two non-code pre-sale blockers above (K·02 crypto review + policy content packs).

### Open follow-ups (ADR candidates / pre-sale blockers)
- **Capture the approving identity (CLOSED 2026-06-12, ADR-0007).** `HITLPort.poll` now returns
  `ApprovalOutcome(decision, decided_by)`; the lifecycle seals the decider as `user:<id>` into
  `LedgerEntry.approver`, surfaced by the ledger-trail API. See the top Log entry.
- **K·02 external cryptographic review (still open, pre-sale critical path).** OpenBao signer adapter
  provides durable Ed25519 signing and the tree/entries are now durably persisted (ADR-0008), but the
  RFC 6962 implementation has not had a third-party crypto review (spec §3.4). On the critical path
  for banks.
- **Durable ledger persistence (CLOSED 2026-06-12, ADR-0008).** `TrustLedger` now write-throughs each
  sealed entry + STH to a `LedgerRepository` (Postgres adapter + migration 003) and rebuilds itself
  on `hydrate()` at startup. Remaining ledger hardening: physical per-tenant tables (current design
  is `tenant_id`-keyed, matching `quaicu_actions`) + the crypto review above.
- **Policy content packs.** K·14 regmap catalog + K·01 CEL engine exist, but no actual RBI / EU AI
  Act / DPDP rule sets are written. The kernel enforces rules; the rules themselves are unwritten.
- **Operator console hardening.** The `console/` web UI ships (policy admin · dashboard · audit ·
  approvals) with **OIDC login (Auth Code + PKCE) + per-tier UI gating** (token-paste remains a dev
  fallback). Remaining: no model-registry (K·08) / consent (K·04) / tenant-config surfaces yet; no
  silent token refresh (re-login on id_token expiry); HITL approval→action-resumption needs the async
  K·06 deployment (the synchronous lifecycle times a gate out). Charts are minimal CSS.

---

## Go-live readiness assessment — PM review (2026-06-16)

A product-manager go-live review against two target markets — **(A) regulated enterprise**
(banks / RBI / EU AI Act / DPDP) and **(B) cloud marketplace SaaS** (AWS/Azure/GCP). Derived from a
full-codebase knowledge-graph pass (`graphify-out/`: `graph.html` · `GRAPH_REPORT.md` · `graph.json` —
3,349 nodes / 245 communities, mapping ~1:1 to the 14 layers + delivery surfaces) plus this journal.
**Bottom line: the governance *engine* is shippable** (code-complete, 861 green, fail-closed
throughout, and the differentiators — RFC 6962 ledger, crypto-shredding erasure, regulator-verifiable
proof export, RLS tenant isolation — are actually built), **but the *product* is not yet live-able to
either market.** The remaining work is bounded packaging/operability + two non-code gates, not
research.

### Readiness scorecard
| Dimension | State | Verdict |
|---|---|---|
| Governance engine (14 layers) | code-complete, conformance-tested | 🟢 ready |
| Security (fail-closed · RBAC · OIDC · tenant isolation) | built & tested | 🟢 ready |
| Auditability (ledger · proof export · erasure) | built | 🟢 differentiator |
| Reproducible build / packaging | **no `pyproject.toml` / lockfile — deps pinned only in `delivery/docker/Dockerfile`** | 🔴 blocker |
| Horizontal scale / HA | in-memory action repo → `--workers 1` hardcoded; in-memory `EntitlementStore` (plans lost on restart) | 🔴 blocker |
| SaaS multi-tenant plane | `TieredKernelProvider` exists but **no production entrypoint** — only the single-kernel path boots | 🔴 blocker (SaaS) |
| CI/CD · SBOM · image signing · vuln scan | none (`.github/workflows` absent) | 🔴 blocker (marketplace) |
| Commercial/legal (LICENSE · SECURITY.md · README · pricing) | absent | 🔴 blocker (listing) |
| K·02 cryptographic review (RFC 6962 ledger) | not done — third-party, ~6–8wk lead | 🔴 regulatory critical path |
| Policy content packs (RBI / EU AI Act / DPDP rules) | engine enforces; **rules unwritten** | 🔴 regulatory critical path |

### The two tracks have different blockers
- **Track A — regulated enterprise (banks).** Gated by two *non-code* items: (1) an **independent
  cryptographic review** of the K·02 ledger — procurement/risk won't accept an unaudited Merkle tree;
  this is the **longest lead time in the whole program (~6–8wk), so commission it first**; and (2)
  **≥1 populated policy pack** — the engine ships empty, so a demo can't show "DPDP consent enforced"
  without live-authored rules. An empty enforcement engine doesn't sell to a regulator; a populated one
  does.
- **Track B — cloud marketplace SaaS.** Gated by *operability*, not regulation: cannot run a billable
  SaaS on `--workers 1` + in-memory state (a pod restart resets every customer's paid tier — a
  billing-integrity failure, not just an HA nit); the shared-plane provider needs a **production
  entrypoint** before "multi-tenant SaaS" is even true; marketplaces require **CI + SBOM + signed
  images + vuln scan** and a **LICENSE** before they will list.

### Recommended sequencing
- **P0 — unblock everything (week 1, in parallel):** (1) **kick off the K·02 crypto-review engagement**
  (pure lead-time — every week of delay slips the bank deal); (2) add **`pyproject.toml` + lockfile**
  (single source of truth for the deps currently buried in the Dockerfile; prerequisite for SBOM,
  reproducible builds, and the installable package); (3) **durable `EntitlementRepository`** (plans must
  survive restart before charging anyone).
- **P1 — make it operable (weeks 2–4):** (4) production entrypoint for `TieredKernelProvider` (the
  actual SaaS plane); (5) replace the in-memory action repo with the Postgres path so `--workers > 1` /
  HA is real; (6) minimal CI: test → ruff → build → SBOM → sign → scan.
- **P2 — make it sellable (parallel, weeks 2–6):** (7) one end-to-end **policy pack** (recommend
  **DPDP** — consent is already enforced, shortest demo-to-value); (8) LICENSE · SECURITY.md · README ·
  marketplace listing assets.

**Single most important call:** A's blockers (crypto review + policy packs) and B's blockers (packaging
+ HA + SaaS entrypoint) barely overlap — run both tracks concurrently. The **external crypto-review lead
time is the longest pole**, so commissioning it is the decision to make today regardless of which market
is prioritized.

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
| 2 | Inference adapters | `adapters/inference/` | adapter-inference | **done** | InferencePort (frozen) | conformance |
| 2 | HITL adapters | `adapters/hitl/` | adapter-hitl | **done** | HITLPort (frozen) | conformance |
| 2 | Storage adapter | `adapters/storage/` | adapter-storage | **done** | StoragePort (frozen) | conformance |
| 2 | Identity adapters | `adapters/identity/` | adapter-identity | **done** | IdentityPort (frozen) | conformance |
| 3 | K·06 Process Engine | `core/process/` | process-agent | **done** | K·03 | §6 (K·06) |
| 3 | Workflow adapters | `adapters/workflow/` | adapter-workflow | **done** (in-memory; Temporal pending) | WorkflowPort, K·06 | conformance |
| 3 | K·04 DPDP Consent | `core/consent/` | consent-agent | **done** | K·02 | §6 (K·04) |
| 4 | K·08 Model Registry | `core/registry/` | registry-agent | **done** | K·05 | §6 (K·08) |
| 4 | K·09 Fairness | `core/fairness/` | fairness-agent | **done** | K·08, K·02 | §6 (K·09) |
| 4 | K·10 Drift | `core/drift/` | drift-agent | **done** | K·08, K·02 | §6 (K·10) |
| 4 | K·11 Explainability | `core/explain/` | explain-agent | **done** | K·08, K·02 | §6 (K·11) |
| 5 | K·13 Sandbox | `core/sandbox/` | sandbox-agent | **done** | K·01, K·02 | §6 (K·13) |
| 5 | K·12 Incident | `core/incident/` | incident-agent | **done** | K·06, K·02 | §6 (K·12) |
| 5 | K·14 Regulatory Mapping | `core/regmap/` | regmap-agent | **done** | K·01, K·02 | §6 (K·14) |
| ↳ | Delivery (SDK · API · Docker) | `delivery/` | delivery-agent | **done** | per delivered layer | §6, §8 |

> **Forward dependency (RESOLVED 2026-06-11):** K·01's activation gate (F-10) needs K·13's
> counterfactual backtest. The bridge now exists — `core/sandbox/bridge.assemble_impact_report`
> turns a `SandboxRun` (+ optional K·09 `FairnessDelta`) into the `ImpactReport` that
> `PolicyStore.activate` consumes, and `POST /v1/policies/{id}/versions/{v}/simulate` runs the
> backtest end-to-end over the tenant's sealed ledger entries (see the top Log entry).

---

## Log (append-only — newest first)

Each entry: date · unit · agent · what changed · what it now exposes · follow-ups.

- **2026-06-25 · W6-7 Step Functions WorkflowPort adapter → AWS parity complete · adapters/workflow + delivery/sdk · claude** —
  Full ASL-translation adapter. `governed_def_to_asl` translates a `GovernedProcessDef` to Amazon States
  Language (steps→Task, transitions→Choice, HITL gate→long-timeout Activity Task + States.Timeout catch,
  TERMINAL_*→Succeed/Fail). `StepFunctionsWorkflowAdapter` implements `WorkflowPort` (create+start_execution
  / send_task_success-failure via the HITL activity token / describe_execution→ProcessState), lazy boto3 +
  injectable client, fail-closed. Registered `aws_sfn`. **Exposes:** run the governed lifecycle natively on
  AWS Step Functions — completes AWS parity (Bedrock + EventBridge + KMS signer + Cognito + SFN). Tests
  (ASL structure + start/state/signal via fake client + missing-boto3) 168 passed. **Follow-ups:** HITL
  task-token needs an activity worker in-deploy; not validated against live AWS.
- **2026-06-24 · W6-7 AWS KMS ledger signer + Cognito-via-OIDC · adapters/ledger + delivery/sdk · claude** —
  The FIPS-HSM signing root on AWS. `adapters/ledger/aws_kms.py` mirrors `gcp_kms.py`: `AwsKmsTreeSigner`
  (ECDSA-P256 via `kms.sign` over a SHA-256 digest → DER signature; local verify against the KMS public
  key) + `AwsKmsLedgerAdapter` (TrustLedger wrapper). Same DER-ECDSA-P256 wire format as the GCP signer,
  so AWS-signed STHs verify with the existing offline regulator code. Registered `aws_kms_ledger` +
  `_DURABLE_LEDGERS`. Cognito needs no code (federates via the existing `OIDCIdentityAdapter`) —
  documented in kernel.gcp.toml. boto3 lazy ([aws]); test uses a real-EC-P256-backed fake KMS client
  (roundtrip + tamper + ledger seal→STH verify), 44 passed. **Exposes:** run the K·02 ledger signing
  root on AWS KMS (+ Cognito SSO) with the same regulator-verifiable proofs. **Follow-ups:** Step
  Functions WorkflowPort adapter (last W6-7 piece); not validated against live AWS KMS.
- **2026-06-24 · W6-6 console ledger-export UI · console · claude** —
  Frontend-only; the export API + offline verifier already existed. Audit page gains Download CSV
  (client-side, RFC-4180, from the loaded trail) and Download proof bundle (JSON) (fetches
  `/v1/ledger/{tenant}/export` → the self-verifying RFC-6962 bundle), with busy/error states. New
  `api.exportLedger()` + `LedgerProofBundle` type. **Exposes:** regulators/analysts can download the
  audit trail + a self-verifying proof bundle from the console. `npm run build` clean. **Follow-ups:**
  verify-by-upload UI; window/regulation export filters.
- **2026-06-24 · W6-5 SIEM fan-out — EventBridge + webhook event sinks · adapters/events + delivery/sdk · claude** —
  Pub/Sub + Logging sinks already existed; added the AWS + provider-agnostic paths. `EventBridgeEventSink`
  (boto3 `put_events`, lazy [aws], injectable client) and `WebhookEventSink` (POST the governed-action
  JSON to any SIEM HTTP collector; injectable poster, default fire-and-forget daemon-thread urllib so a
  slow SIEM never blocks the seal path). Both best-effort. Wired in `Kernel._wire_event_sinks` via
  `[events].eventbridge_bus` and `[events].webhook_url` (+ `${ENV}`-resolved headers); documented in
  kernel.starter.toml. **Exposes:** the governed-action stream now fans out to GCP Pub/Sub, AWS
  EventBridge, or any HTTP SIEM. Tests (fake events client + injected poster + wiring) 214 passed.
  **Follow-up:** queued/at-least-once delivery; not validated against live EventBridge.
- **2026-06-24 · W6-4 provable erasure — HSM GcpKmsShredKeyring + durable store + wiring · adapters/erasure + delivery/sdk + migration · claude** —
  Erasure DEKs lived in memory and erasure wasn't wired on the SaaS plane (build_saas_app omitted
  erasure_engine → 503). New `GcpKmsShredKeyring` (envelope: per-subject DEK wrapped by a Cloud KMS
  symmetric KEK; only the wrapped blob persists; destroy deletes it + tombstones → unrecoverable),
  injectable `WrappedDekStore` with `InMemoryWrappedDekStore` + durable `PostgresWrappedDekStore` on
  migration 012 (`quaicu_shred_keys`). `delivery/sdk/erasure_config.build_erasure` reads `[erasure]`
  (keyring=memory|gcp_kms, kek, dsn) with fail-safe fallbacks; `build_saas_app` now wires it. Lazy
  google-cloud-kms, injectable client. **Exposes:** HSM-rooted provable crypto-shred + a working erasure
  endpoint when enabled. Tests (full cycle via ErasureEngine w/ fake KMS; DEK-wrapped-at-rest;
  no-resurrection; Postgres fake-cursor; config) 164 passed. **Caveats/follow-ups:** prod needs [gcp] +
  a KEK + migration 012 + DSN; not validated against live KMS; AWS KMS keyring later.
- **2026-06-24 · W6-3 PII masking beyond regex — MaskingPort + Cloud DLP · core/ports + core/gateway + adapters + delivery · claude** —
  Made the gateway's PII-detection engine swappable. New `MaskingPort` protocol (`core/ports/masking.py`,
  async `mask`); default `RegexMaskingAdapter` (wraps the existing regex `mask_text`, exported as
  `DEFAULT_MASKING`); managed `CloudDLPMaskingAdapter` (`adapters/masking/gcp_dlp.py`) — lazy
  `google-cloud-dlp` ([gcp] extra, injectable client), `inspect_content` findings tokenized into the same
  `MaskingContext` (rehydration unchanged), off the event loop. Wired on `app.state.masking_port` (regex
  default; opt into DLP via `QUAICU_MASKING_PROVIDER=dlp` + `QUAICU_DLP_PROJECT`, fail-safe fallback); the
  BYO gateway route now `await port.mask(...)`. **Exposes:** managed PII detection (names/addresses regex
  misses) as a drop-in, opt-in engine. Tests (regex + DLP via fake client + missing-SDK + route-uses-port)
  284 passed. **Follow-ups:** AWS Comprehend adapter; adopt the port in K·05 `AIGateway.generate`; DLP
  batching. Not validated against live DLP.
- **2026-06-24 · W6-2 provider shim ④ AWS Bedrock → W6-2 complete · delivery/api + core/account + console · claude** —
  Final BYO-gateway shim. `BedrockShim` is self-dispatching (own `complete`/`stream`, not the httpx
  path) because boto3 owns the SigV4 Converse call. Lazy `import boto3` ([aws] extra) + injectable client
  (per `marketplace.py`); pure `openai_to_converse`/`converse_to_openai` translators; `complete` via
  `asyncio.to_thread(client.converse)`; `stream` bridges boto3's blocking `converse_stream` EventStream
  onto an asyncio.Queue → OpenAI chunks + [DONE]. Route branches on `hasattr(shim,"complete")` →
  PROVIDER_DEPENDENCY_MISSING (501) / PROVIDER_AUTH_FAILED (502). New `AIConnection.aws_access_key_id`;
  console Bedrock form; coming-soon panel → "supported providers". **Exposes:** the gateway now governs
  OpenAI-compatible + Azure + Anthropic + Vertex + Bedrock — one governed endpoint across every major
  provider. Tests (translators + complete/stream with a fake client + missing-boto3 + e2e + account)
  256 passed, console builds. **Caveats:** Bedrock in prod needs the [aws] extra; not validated against
  live AWS. **Follow-ups:** Bedrock tool-calls/vision; install [aws] in the SaaS image to enable it.
- **2026-06-23 · W6-2 provider shim ③ Google Vertex · delivery/api + core/account + console · claude** —
  First provider with cloud-IAM auth. `VertexShim`: per-tenant service-account JSON (encrypted) → cached,
  off-event-loop OAuth token (google-auth, no new dep) → Vertex's OpenAI-compatible endpoint
  (`/v1beta1/projects/{project}/locations/{location}/endpoints/openapi/chat/completions`); body/response/
  stream stay OpenAI-shaped. `build_request` made async across shims; route maps credential failures to
  PROVIDER_CONFIG_INVALID / PROVIDER_AUTH_FAILED. New `AIConnection.project`/`location`; console Vertex
  form (project/location + SA-JSON textarea). **Exposes:** Vertex as a selectable BYO provider with the
  SA JSON never leaking in status. Tests (token minter patched, no network) + e2e + account round-trip;
  api+account 249 passed, console builds. **Not validated against live Vertex.** **Follow-ups:** ④ Bedrock
  (boto3 + SigV4 + Converse; pairs with W6-7); Vertex tool-calls/vision deferred.
- **2026-06-23 · W6-2 provider shim ② Anthropic · delivery/api + console · claude** —
  Refactored the provider seam into a shim registry (`delivery/api/ai_providers.py`):
  `build_request`/`translate_response`/`translate_stream` per provider. `OpenAICompatShim` (OpenAI-
  compatible + Azure) is identity/passthrough (Azure unchanged); `AnthropicShim` translates OpenAI ⇄
  Anthropic Messages both ways incl. the SSE event format. The gateway route resolves `get_shim(conn)`
  and translates around the unchanged masking/budget/policy/rehydrate logic. Console adds an Anthropic
  preset. **Exposes:** Anthropic as a selectable provider on the BYO gateway. Tests `test_ai_providers.py`
  + e2e; api+account 244 passed, console builds. **Not validated against the live Anthropic API (no key).**
  **Follow-ups:** ③ Vertex (SA JSON→OAuth→OpenAI-compat endpoint), ④ Bedrock (boto3+SigV4+Converse);
  Anthropic tool-calls/vision deferred.
- **2026-06-23 · W6-2 provider shim ① Azure OpenAI · delivery/api + core/account + console · claude** —
  First of four provider shims for the BYO gateway (unified gateway across OpenAI-compatible / Azure /
  Anthropic / Vertex / Bedrock, built one at a time). Added a `_provider_target(conn, model)` seam in
  `ai_gateway.py`: Azure → `api-key` header + `/openai/deployments/{model}/chat/completions?api-version=…`;
  default → OpenAI-compatible Bearer. Azure stays OpenAI-shaped, so masking/budget/streaming are
  unchanged. New `AIConnection.api_version`; console Azure preset + api-version field. **Exposes:** Azure
  OpenAI as a selectable provider. Test green; api+account 238 passed, console builds. **Follow-ups
  (one at a time):** ② Anthropic (translation), ③ Vertex (SA JSON → OAuth → OpenAI-compat endpoint),
  ④ Bedrock (boto3 + SigV4 + Converse; pairs with W6-7).
- **2026-06-23 · W6-2 govern the AI-gateway BYO passthrough · delivery/api + core/account + console · claude** —
  The `/v1/ai/chat/completions` BYO passthrough was ungoverned (verbatim forward after only a policy
  check). Added a **per-tenant PII-masking toggle** (`AIConnection.mask_pii`, opt-in on all tiers; masks
  via `core/gateway/masking.py`, rehydrates the response), **token-budget enforcement** (`app.state.ai_budget`
  `InMemoryBudgetTracker`, 429 on exhaustion, env default cap), and **streaming** (the prior hard 400 →
  an SSE `StreamingResponse` proxy). Console AI-gateway page: masking toggle + status + a "more providers
  — coming soon" panel (Azure/Anthropic pre-order). **Exposes:** governed BYO inference (PII never leaves
  the kernel when masking is on; per-tenant spend cap; streaming works). Tests `test_ai_gateway.py`;
  api+account 237 passed, ruff clean, console builds. **Follow-ups (deferred to next kernel version):** the
  Azure + Anthropic translation shims.
- **2026-06-23 · W6-1 SCIM provisioning + RBAC + team UI · core/account + delivery/api + console · claude** —
  Added multi-user support to a tenant (there was none — one Account + API keys). New: `Member` entity;
  `core/account/roles.py` (OWNER/ADMIN/COMPLIANCE/VIEWER → scopes, + `members:admin`/`scim:admin`);
  engine member lifecycle (deactivation revokes the member's keys via a new `ApiKey.member_id`);
  migration `011_create_members` (+ `api_keys.member_id`); Postgres adapter + store + repository support;
  a **SCIM 2.0** Users endpoint (`/scim/v2`, self-auth on a `scim:admin` bearer, tenant-isolated, Okta
  `active=false` deprovision); a `/v1/members` console API + a console **Team** page. **Exposes:** enterprise
  IdP provisioning/deprovisioning + role-based team management; deprovisioning revokes access.
  Tests: `test_members.py`, `test_scim.py`; full unit suite 946 passed, ruff clean, console builds.
  **Follow-ups:** SCIM Groups, IdP-specific certification, per-member console login (deferred).
- **2026-06-23 · Wave 5 residency/sovereignty — Terraform the SaaS plane + region presets + zero-egress · deploy/terraform + docs · claude** —
  Executed Wave 5 of `ACTION_TRACKER.md`. The SaaS plane had no IaC (hand-deployed). **Code:** new
  `deploy/terraform/gcp-saas/` module codifies the shared-plane Cloud Run service + Cloud SQL + Secret
  Manager, mirroring `gcp-enterprise/`; `var.region`-parameterized with `regions/{eu,india,gulf}.tfvars`
  presets (W5-1/W5-2); opt-in `enable_private_egress` (VPC connector + private Cloud SQL), default off
  (W5-3). **Docs:** `DATA_RESIDENCY.md` (per-region matrix + residency caveats, W5-4),
  `ZERO_EGRESS_VALIDATION.md` (VPC-SC topology + evidence method, W5-3), `WAVE5_RESIDENCY.md` tracker;
  cross-linked `DEPLOY_CLOUD_RUN.md`. **Exposes:** reproducible per-zone SaaS deploys + a path to a
  proven no-egress posture. **Follow-ups (human/ops):** `terraform validate`/apply (TF not installed
  here), import the live service, org-level VPC-SC perimeter, and run the zero-egress validation at
  scale (the remaining honest gap).
- **2026-06-23 · Wave 4 operational readiness — health/readiness probes + CI scanning + ops runbooks · delivery/api + cloudbuild + docs · claude** —
  Executed Wave 4 of `ACTION_TRACKER.md`. **Code (W4-1):** added `/readyz` (readiness, gated on a new
  `app.state.ready` flag flipped at the end of lifespan hydration) alongside the existing `/health`
  (liveness) in `delivery/api/app.py`; Helm readiness probe → `/readyz`; `/readyz` added to the
  rate-limit exempt set; `tests/unit/api/test_health.py`. **CI (W4-9):** `cloudbuild.yaml` now gates
  on lint+unit-tests (blocking) then runs pip-audit + Trivy + a CycloneDX SBOM artifact in report
  mode. **Docs:** new `SECURITY.md` (resolves the dangling refs from Waves 2–3), plus
  `docs/operations/{DR_BCP_RUNBOOK,INCIDENT_RESPONSE,RETENTION_WORM_KEYROTATION,VULN_MANAGEMENT,OBSERVABILITY_ONCALL_STATUS,WAVE4_OPS_READINESS}.md`
  and `docs/compliance/CAIQ_SIG_ANSWERS.md`; corrected an overstated CI claim in the DPA starter.
  **Exposes:** liveness/readiness for orchestrators + uptime monitors; a supply-chain CI gate; a
  ready-to-use ops/security doc set. **Follow-ups (human/ops):** run the DR restore test (the real gap
  behind RTO/RPO), wire external monitoring/status-page/pager, stand up a retention-locked WORM bucket,
  and graduate CI scans report→blocking.
- **2026-06-23 · Wave 3 legal/commercial pack — counsel-briefing starter docs · legal docs · claude** —
  Executed Wave 3 of `ACTION_TRACKER.md` (legal/commercial, all counsel-gated). No code: produced
  five starter docs under `docs/legal/` to compress counsel drafting — `MSA_STARTER.md` (W3-1, 18-clause
  MSA skeleton + 4 exhibits; the load-bearing clause is the *governance-is-tooling-not-a-compliance-
  guarantee* disclaimer), `SLA_STARTER.md` (W3-3, uptime tiers + service-credit schedule, numbers left
  as `[N]%` placeholders gated on W4-1/2/3 observability+tested-DR), `ORDER_FORM_AND_PRICING.md` (W3-4,
  order-form + support tiers + pricing mirroring live ₹10k/₹50k Razorpay), `TERMS_SIGNOFF_INVENTORY.md`
  (W3-5, counsel review checklist for `console/src/legal/content.ts`), `WAVE3_LEGAL_TRACKER.md` (the
  human-item tracker). W3-2 (DPA) is satisfied-by the existing `DPA_ART28_STARTER.md`. **Exposes:** a
  ready-to-hand-to-counsel pack; the binding contracts are still counsel-originated. **Guardrail:** did
  NOT remove the live "draft" banner in `content.ts:1-2` — that is a separate post-sign-off PR.
  **Follow-ups (pure human):** W3-6 insurance (limits feed the MSA liability cap), W3-7 entity/tax
  (gates governing-law + cross-border quoting), W3-8 live Razorpay KYC (+ provision the absent
  `RAZORPAY_WEBHOOK_SECRET`).
- **2026-06-23 · Wave 2 compliance — RBI/SEBI policy pack + commissioning docs · policy packs / compliance docs · claude** —
  Executed Wave 2 of `ACTION_TRACKER.md` (long-lead compliance). **Code (W2-6):** new starter policy
  pack `docs/policy-packs/rbi/{policies.toml,README.md}` — 12 CEL `[[policy.seed]]` rules across 4
  governed action types (`data.store`, `data.transfer`, `outsourcing.engage`, `access.grant`) encoding
  RBI payment-data localization (deny non-IN payment storage), encryption-at-rest, SEBI cloud
  localization (review), RBI material-outsourcing governance (approval + audit-rights + exit-plan),
  cross-border transfer review, and access-logging. Registered the `rbi` `_META` entry in
  `core/policy/packs.py`; added `tests/unit/policy/test_rbi_pack.py`. Mirrors the existing DPDP pack;
  the RBI regime was already modeled (`core/regmap/model.py` → `Regime.RBI_FREE_AI`). **What it
  exposes:** a third importable regulatory pack — `get_pack("rbi")` / `list_packs()` now returns
  `['dpdp','eu-ai-act','rbi']`; tenants can import it (DRAFT → backtest → ACTIVATE) for an RBI/SEBI
  baseline. **Docs (commission the human clocks):** finalized the K·02 crypto-review RFQ with a
  send-ready commissioning checklist + vendor shortlist (`docs/operations/CRYPTO_REVIEW_RFQ.md` §6,
  W2-1); PCI SAQ-A scope memo (`docs/compliance/PCI_SAQ_A_SCOPE.md`, W2-7); pen-test SoW
  (`docs/compliance/PENTEST_SOW.md`, W2-3); GDPR Art.28 DPA starter (`docs/legal/DPA_ART28_STARTER.md`,
  W2-5, not-legal-advice); Wave-2 clock tracker (`docs/compliance/WAVE2_COMPLIANCE_CLOCKS.md`).
  **Verification:** `test_rbi_pack.py` 14/14, `tests/unit/policy` 82 passed, ruff clean. **Follow-ups:**
  RBI pack is a DRAFT baseline — adapt to licence category + backtest before activating in a real
  tenant; W2-1/3/5/7 are drafted-and-pending the human send/book/counsel/QSA step; W2-2 (SOC 2) + W2-4
  (ISO 27001) remain pure-human; W2-8 (HIPAA) deferred. (Also still open from prior session: W6-9
  console fonts/headers need `wrangler deploy`; `RAZORPAY_WEBHOOK_SECRET` absent from the Cloud Run env.)

- **2026-06-23 · Review triage — consolidated action tracker from two independent reviews · planning docs · claude** —
  Merged two independent 2026-06-23 reviews — Gemini's code/runtime review (`review finding gemini.md`)
  and the regulated-sale readiness review (`REVIEW_FINDING.md`) — into one trackable sheet
  **`ACTION_TRACKER.md`** (repo root, `C:\alis-antigravity\Kernel\ACTION_TRACKER.md`). Organized into 9
  act-on-order waves: **W0** live risk (rotate leaked Resend + Razorpay test secrets, confirm
  `QUAICU_API_KEY_PEPPER`), **W1** the one all-sources-confirmed code fix (real-client-IP rate limiting
  behind the Cloudflare Worker — key on `CF-Connecting-IP`, not raw `X-Forwarded-For`), **W2** long-lead
  compliance clocks (K·02 crypto review, SOC2, pen-test, ISO 27001, GDPR/RBI/PCI), **W3** legal pack
  (MSA/DPA/SLA + counsel sign-off + Razorpay KYC), **W4** ops readiness (observability, status page,
  tested DR, IR runbook, trust center), **W5** residency/multi-region + zero-egress validation, **W6**
  product gaps (SSO/SCIM, MaskingPort, `GcpKmsShredKeyring`, SIEM fan-out, AWS parity, auto-billing,
  console hygiene), **W7** GTM (design partner / reference customer), **W8** deferred perf (Gemini's
  sync-HTTP OpenBao signer + sync lifespan hydration + Go polyglot split). **What it exposes:** every row
  carries an ID (W0-1…), a source tag (G/R/Both), a type (code vs human/process), a status field, and a
  dated progress log — so work proceeds top-to-bottom with tracking. **Follow-ups (none actioned yet):**
  highest-confidence item is **W1-1** (real-client-IP rate limiting — flagged independently by Gemini §1,
  readiness §5, *and* the CLAUDE.md 2026-06-16 handoff). **W0-1** (rotate the leaked secrets) is the only
  live-exposure item. Long-lead clocks (W2) should start **in parallel now** per the readiness review's
  TOP-5 critical path — don't let finished code work crowd out the compliance clock. No code/test/config
  touched.

- **2026-06-17 · Launch hardening — RLS hydration sentinel + integration CI · adapters/ledger · migrations · .github · claude** —
  Final launch bucket (D). **(1)** Replaced the per-startup `ALTER TABLE … NO FORCE/FORCE` hydration
  hack (ACCESS EXCLUSIVE lock per boot, needs table ownership) with a **read-only RLS sentinel**
  (migration 007): the tenant-isolation `USING` clause also matches `app.current_tenant = '*'`, while
  `WITH CHECK` stays strict — cross-tenant *read* for hydration, never cross-tenant *write*. `'*'` is
  unreachable via the per-request path (tenant ids are validated). Works on Cloud SQL without
  BYPASSRLS/superuser. **Verified live**: migration 007 applies + the 6 Postgres conformance tests
  pass (hydrate-after-restart + cross-tenant isolation). **(2)** New CI `integration` job: a postgres:16
  service container runs migrations 001–007 + the storage/ledger conformance suite (`-m integration`)
  on every PR (Cloud KMS/OpenBao still self-skip). Suite 940/14, ruff clean. **Remaining (human):**
  merge + tag a release (`release.yml` publishes the cosign-signed `ghcr.io/<owner>/kernel:<tag>`);
  commission the K·02 crypto review (RFQ drafted); finalize LICENSE/SECURITY/PRICING.

- **2026-06-17 · Integration tests verified live on GCP (Cloud SQL + Cloud KMS) · tests · claude** —
  Resolved the 10 skipped integration tests against real GCP. **(1)** Ran the 6 Postgres conformance
  tests (`tests/conformance/storage/test_spec.py` + `ledger/test_postgres_spec.py`) against the live
  **Cloud SQL** instance via the Auth Proxy (ADC) → all pass (validates Gemini's RLS fix end-to-end).
  **(2)** Added + ran `tests/conformance/ledger/test_gcp_kms_spec.py` against live **Cloud KMS** — the
  managed-service replacement for OpenBao. The target key (`quaicu-ledger/sth-signer` v1, ECDSA P-256,
  us-central1) was `DESTROY_SCHEDULED` from the prior revert; **restored + enabled** it (the adapter
  had correctly fail-closed with `LedgerSealError` while it was disabled) → all 4 KMS tests pass. **Full
  suite with both backends: 925 passed / 4 skipped** (the 4 skips are now only the OpenBao tests —
  OpenBao kept as the sovereign/air-gapped option but not the live GCP signer). See [[integration-db]]
  for run commands. **Follow-up:** a CI job that provisions Postgres + points KMS at a key via secrets
  so the integration layer runs automatically on PRs.

- **2026-06-17 · CEL policy authoring guide for client AIs (reverted the in-product AI assistant) · docs · claude** —
  Product call: instead of an in-product NL→CEL assistant (model cost/ops to run), ship a **shareable
  context file** clients paste into their own AI (ChatGPT/Claude/Gemini) to draft compatible CEL.
  **Reverted** the AI-assistant feature (`core/policy/authoring.py`, route `/v1/policies/assist`,
  config wiring, tests — revert of `0dbe302b`). **Added** `docs/CEL_POLICY_GUIDE.md`: the exact
  activation schema (only `action_type`, `action_tenant`, `actor_id`, `actor_roles`, `payload_<field>`
  — no built-in time/context vars), decision values + deny-overrides + fail-closed, celpy syntax
  cheat-sheet, gotchas (dot-free payload names, no invented functions, one boolean expr), output JSON
  format, worked examples, and the draft→backtest→activate reminder. Suite **915 passed / 10 skipped**,
  ruff clean. No code/API change.

- **2026-06-17 · Event sinks for DB-less audit + postgres RLS unit-test repair · adapters/events · delivery/sdk · tests · claude** —
  **(1) Event sinks (K·07):** `adapters/events/sinks.py` — `LoggingEventSink` writes one structured
  audit line per sealed governed action to the `quaicu.audit` logger (→ Cloud Logging), and
  `PubSubEventSink` fans out to GCP Pub/Sub (lazy `[gcp]`, best-effort). Wired config-driven in
  `Kernel.from_config` via `[events].log_sink` / `[events].pubsub_topic` (`_wire_event_sinks`), and
  **enabled on the STARTER/free tier** (`kernel.starter.toml`) so the in-memory-ledger free tier still
  has a durable, queryable record of every governed decision with **no database** — the platform log
  stream is the audit substrate. **(2)** Repaired the 10 unit-test failures introduced by the postgres
  RLS fix (`b8d12126`, gemini): `_fake_pool` now models `conn.transaction()` as an async CM (storage +
  ledger), the deadlock test sets its raising txn after the helper, and the append test expects 2
  executes (set_config + insert). Suite **915 passed / 10 skipped**, ruff clean. **Follow-up:** the
  ledger hydration RLS bypass uses `ALTER TABLE … NO FORCE/FORCE` per startup (needs the runtime role
  to own the tables + takes ACCESS EXCLUSIVE locks); prefer a `BYPASSRLS` role + `SET LOCAL
  row_security = off`.

- **2026-06-16 · Metering activation + shared Redis meter + Marketplace metering scaffold + hosting docs · delivery · adapters/metering · adapters/billing · claude** —
  Go-live SaaS plumbing. **(1) Metering gap closed:** `UsageMeter` is now wired into both entrypoints
  (`delivery/entrypoint.py`, `delivery/sdk/saas_app.py`) via a config-driven `build_usage_meter`
  (`delivery/sdk/metering_config.py`) — so daily-quota enforcement (`max_actions_per_day`) + admin
  usage snapshots are live, not dormant. **(2) Shared meter:** `adapters/metering/redis_meter.py`
  (`RedisUsageMeter`) is a drop-in for the in-process meter giving exact cross-replica counts; selected
  by `[metering].redis_url` / `REDIS_URL` (optional `[redis]` extra, lazy import, fully tested with a
  fake client). **(3) Marketplace metering (scaffold):** `adapters/billing/marketplace.py`
  (`MarketplaceMeteringReporter`) computes per-tenant usage deltas from any `UsageMeter` and reports
  them best-effort; the cloud API call is an injected `send` seam with `gcp_sender` (Service Control) /
  `aws_sender` (BatchMeterUsage) lazy-SDK scaffolds. Delta/rollover/retry logic fully tested; cloud
  send left as a marked seam. **(4) Hosting docs:** `docs/HOSTING.md`, `docs/DEPLOYMENT_MODELS.md`
  (Model A you-host vs Model B customer-host), `docs/GO_LIVE_SETUP.md` (frontend/console, Stripe/Razorpay,
  DB, OIDC, TLS, checklist). Suite **910 passed / 10 skipped**, ruff clean. **Follow-ups:** wire a
  scheduler (Cloud Scheduler/EventBridge/ARQ) to call `report_all` periodically; finish the cloud
  `send` seams against the real SDKs; still-specified cloud adapters (DLP masking port, KMS erasure,
  Pub/Sub, Cloud Workflows HITL, IaC).

- **2026-06-16 · Enterprise Cloud Strategy + reference cloud adapters (GCP-first) · adapters/ledger · adapters/inference · core/regmap · claude** —
  Marketplace-readiness work for regulated buyers (banks/insurance/healthcare) who won't self-host
  OpenBao/Kafka/Temporal. **(1) Security pass already landed earlier today** (4 code-review findings:
  rate-limit DoS, OpenBao verify(), event-bus logging, API-key HMAC+pepper). **(2) Two reference
  cloud adapters, fully tested with mocked clients (no cloud creds in CI):** `adapters/ledger/gcp_kms.py`
  (`GcpKmsTreeSigner` + `GcpKmsLedgerAdapter`, registry `gcp_kms_ledger`) signs STHs in Cloud KMS
  (FIPS 140-2 L3 HSM); `adapters/inference/vertex.py` (`VertexInferenceAdapter`, registry
  `vertex_inference`) routes to Vertex AI (Gemini). **(3) Crypto change (ADR-0012):** GCP Cloud KMS has
  **no Ed25519**, so the KMS signer uses **ECDSA P-256**; the offline regulator verifier
  (`core/regmap/export.py`) is now **algorithm-aware by public-key type** (Ed25519 vs ECDSA-P256) — no
  `SignedTreeHead` field, no storage migration; existing Ed25519/OpenBao paths unchanged. **(4)** Optional
  `[gcp]`/`[aws]` extras in `pyproject.toml` (SDKs imported lazily, core stays SDK-free); new
  `delivery/docker/kernel.gcp.toml` profile. **Exposes:** `docs/strategy/ENTERPRISE_CLOUD_STRATEGY.md`
  (full GCP-first plan, AWS parity) + `docs/adr/0012-cloud-native-adapters.md`. Suite **897 passed / 10
  skipped**, ruff clean. **Follow-ups (specified, not coded):** `MaskingPort` + Cloud DLP/Comprehend
  adapter (masking is still concrete regex — the one un-ported component); KMS-envelope `ShredKeyring`;
  Pub/Sub `EventPort`; Cloud Workflows/Step Functions HITL; Marketplace Metering billing adapter;
  Terraform/Deployment Manager IaC. **K·02 external crypto review must now cover the ECDSA-P256 STH path.**

- **2026-06-16 · Go-live engineering build — packaging + durable entitlements + SaaS entrypoint + HA + CI · pyproject · adapters/entitlements · delivery** —
  Closed the **code-completable** go-live blockers from the PM review (engineering only; the DPDP pack,
  LICENSE/docs, K·02 crypto review, and pricing stay human-owned). **(A) Packaging:** new
  `pyproject.toml` (PEP 621) is now the single source of truth for deps — previously pinned only in the
  Dockerfile *and* the CI workflows, and **missing `opentelemetry-api`** (a hard import in
  `core/consent/engine.py`), now declared. `starlette` (imported directly) added; `pyyaml` dropped
  (unused — kept transitively via cel-python). Pinned+hashed `requirements.lock` generated via
  `uv pip compile --generate-hashes` (42 dists); Dockerfile builder rewritten to
  `pip install --require-hashes -r requirements.lock` + `pip install --no-deps .` (reproducible build;
  registers the `quaicu-kernel` / `quaicu-kernel-saas` console scripts). The former repo-root
  `pyproject.toml` (partial deps, the pytest/ruff config) was **removed**; the authoritative one lives
  at `New/quaicu-kernel/` (matching the Docker context), with the pytest/ruff/mypy config moved into it
  (pytest rootdir now binds there). Wheel builds clean (core/adapters/delivery + both scripts).
  **(B) Durable entitlements:** the only missing durability piece — `EntitlementStore` write-through +
  `BillingEngine`'s `*_persisted` calls already existed, but nothing backed them. Added migration `005`
  (`quaicu_customer_plans`), `adapters/entitlements/postgres.PostgresEntitlementRepository` (mirrors the
  policy adapter; fail-closed `EntitlementPersistenceError`), a `build_entitlement_store(config)` builder
  (`[entitlements].dsn` → `[storage].dsn` fallback, `${ENV}`-resolved), wired into `delivery/entrypoint.py`,
  and **entitlement-store hydration in create_app's lifespan** — so a billing-driven tier flip now
  survives a restart. **(C) SaaS-plane entrypoint:** `delivery/sdk/saas_app.build_saas_app` (pure,
  testable) + `delivery/entrypoint_saas.py` (CLI `quaicu-kernel-saas`) build a `TieredKernelProvider`
  from a `[plane]` descriptor — the shared multi-tenant plane finally has a production entrypoint
  (it was build-only before). Example `kernel.saas/starter/business.toml`. **(D) HA:** new all-durable
  `kernel.prod.toml` (postgres storage/ledger/policy + durable entitlements — no correctness-critical
  in-process state), Dockerfile `CMD` now honours `KERNEL_WORKERS` (default 1; safe >1 only with the
  durable profile). **Follow-up noted:** the usage meter + in-memory event bus are per-process, so exact
  cross-worker metering needs a shared meter/broker (best-effort, never over-counts; dashboard reads from
  the durable ledger so is unaffected). **(E) CI/CD:** the existing `.github/workflows` (which my
  assessment wrongly called absent) already did GHCR push + BuildKit SBOM/provenance + cosign keyless
  signing — improved them to install from `pyproject` (kills the same dep drift + missing otel), added a
  **ruff lint** gate to CI and a **Trivy HIGH/CRITICAL scan** gate to release. **Tests:** +20
  (`test_postgres_repository.py`, `test_entitlements_config.py`, `test_saas_entrypoint.py`); suite
  861 → **881 passed / 10 skipped**, ruff clean, wheel + lock verified. Branch `feat/go-live-engineering`.

- **2026-06-16 · Go-live readiness assessment (PM review) · docs/adr · graphify-out** —
  Added a product-manager go-live review — see the new section **"Go-live readiness assessment — PM
  review (2026-06-16)"** above the Work queue. Scores readiness against two markets (regulated
  enterprise vs cloud marketplace SaaS) and sequences the remaining work P0–P2. Backed by a
  full-codebase knowledge-graph pass written to `graphify-out/` (`graph.html` · `GRAPH_REPORT.md` ·
  `graph.json` — 3,349 nodes / 245 communities, ~1:1 to the 14 layers). **Key finding:** the engine is
  code-complete and green, but live-ability is blocked by **packaging** (no `pyproject.toml`/lockfile —
  deps live only in the Dockerfile), **operability** (in-memory action repo + `EntitlementStore` →
  `--workers 1`, paid plans lost on restart), **no SaaS-plane production entrypoint**, **no
  CI/SBOM/signing/LICENSE**, and the two known non-code gates (K·02 crypto review + policy content
  packs). Longest pole = the external crypto-review lead time → commission first. **No code changed —
  strategy/record only.**

- **2026-06-15 · WS-C billing productionized — config-driven wiring + console upgrade page · delivery/sdk · delivery/console** —
  Made the billing edge turnkey: it now boots from config + environment (no longer test-only) and a
  tenant can self-serve upgrade from the console. **Backend wiring:** new
  `delivery/sdk/billing_config.py` — `build_billing(config, entitlements)` turns a `[billing]` TOML
  section into the live `billing_adapters` + `BillingEngine`, reusing the existing adapter
  constructors. Secrets are `${ENV_VAR}` references resolved at load (`os.path.expandvars`) so live
  payment keys never sit in the committed file; provider price/plan tables map to `FeatureTier`
  (fail-closed on an unknown tier); a configured provider missing `webhook_secret` raises at boot
  (never silently disabled). `delivery/entrypoint.py` now reads the TOML and, **only when a
  `[billing]` section exists**, builds a shared `EntitlementStore` and passes
  `entitlement_store` + `billing_adapters` + `billing_engine` to `create_app` — the same store a
  verified webhook mutates and the entitlements/rate-limit edge reads (one source of truth for plans).
  Absent `[billing]`, the kernel serves exactly as before. Documented the full section in
  `kernel.example.toml`. **Provider discovery:** `GET /v1/me/entitlements` now returns
  `billing_providers` (the checkout-capable adapters, via `isinstance(..., CheckoutPort)`), so the
  console offers only configured providers. **Console:** new **Billing** page (`console/src/pages/Billing.tsx`)
  + `/billing` route and a nav link shown only when `billing_providers` is non-empty — shows the
  current tier, the upgrade targets (tiers above the current one; both paid tiers when there's no
  active plan), an optional provider selector, and an "Upgrade to X" button that calls
  `POST /v1/billing/checkout` and **redirects to the provider's hosted payment page**
  (`window.location.assign`), with a return banner on `?upgraded=1`/`?cancelled=1`. `customer_email`
  is omitted (the providers collect it). `api.checkout()` + `CheckoutRequest`/`CheckoutResponse`
  types added; `npm run build` (tsc strict + vite) green. **Tests:** +10 (`test_billing_config.py` —
  absent/empty no-op, stripe/razorpay/both built, `${ENV}` substitution, missing-secret + bad-tier
  fail-closed, webhook-only-not-checkout-capable; `test_entitlements.py` — `billing_providers`
  reported/empty); suite 851 → **861**. **The payment gateway is now configurable end-to-end and
  reachable from the UI.** **Follow-ups:** wire billing into the shared-plane `TieredKernelProvider`
  composition (the single-kernel entrypoint is done; the provider has no production entrypoint yet);
  durable `EntitlementRepository` so plans survive restart; a console "manage subscription" (provider
  billing-portal) link.

- **2026-06-15 · WS-C checkout / subscription creation — outbound payment initiation · core/billing · adapters/billing · delivery** —
  Closed the WS-C follow-up: the kernel only *consumed* provider webhooks (inbound) and never
  *initiated* a payment, so it could flip a tier but not sell one. Added the **outbound** half.
  New `CheckoutPort` protocol (`core/billing/port.py`) kept **separate** from `BillingPort` so the
  webhook-verification path stays pure/synchronous (HMAC only) while checkout — which must call the
  provider REST API — is async behind an **injectable HTTP transport** (`adapters/billing/_http.py`;
  stdlib `urllib` run in a thread by default → **no SDK, no new dependency**, fully testable without a
  processor). New `CheckoutSession` model + `CheckoutError` in the frozen `core/errors.py`. Both
  adapters implement `create_checkout`: **Stripe** creates a Checkout Session
  (`mode=subscription`, form-encoded, Bearer key) and **stamps `subscription_data[metadata][tenant]`**;
  **Razorpay** creates a subscription (Basic auth, JSON) and **stamps `notes.tenant`**, returning the
  hosted `short_url` — i.e. each stamps the tenant exactly where its own inbound webhook reads it back,
  so checkout→webhook→tier-flip is a closed loop. New route `POST /v1/billing/checkout` — the
  **authenticated, tenant-isolated, `billing:write`-scoped** counterpart to the signature-authed
  webhook: it always bills the *authenticated* tenant (`get_request_tenant`), rejects STARTER/unknown
  tiers (422), unconfigured providers (503), and provider failures (502). New `billing:write` scope.
  **Narrowed the auth/rate-limit exemption** from `/v1/billing` to `/v1/billing/webhook` so checkout
  is API-key-protected and rate-limited (only the webhook, authed by provider signature, is exempt).
  **Tests:** +16 (`test_checkout.py` — Stripe/Razorpay request shape incl. tenant-stamp, auth header,
  not-configured / unmapped-tier / provider-error; `test_billing_checkout.py` — 401/200/422/503/502 +
  the exemption-narrowing assertion that checkout needs a key while the webhook stays exempt); suite
  835 → **851**. **The payment gateway is now end-to-end** (initiate → pay → webhook → tier flip).
  **Follow-ups:** checkout-session creation is unauthenticated-of-the-*provider* config (api keys are
  deployment secrets — no production wiring/factory yet, adapters are constructed in code/tests); a
  console "Upgrade" button calling this route; emit a K·07 event on checkout creation for the trail.

- **2026-06-15 · Console OIDC login + per-tier UI gating · delivery/console · delivery/api (WS-D, Wave-2)** —
  Closed the last Wave-2 code slice: the operator console moves from token-paste to a real
  **OIDC Authorization Code + PKCE** login against the named IdP connectors (`adapters/identity/oidc.py`),
  and gates its UI by the tenant's commercial tier. **Backend:** new read-only route
  `GET /v1/me/entitlements` (`delivery/api/routes/entitlements.py`) returns the caller's tier + a
  feature-flag/quota map **derived from `TIER_MATRIX`** (single source of truth — the console never
  hard-codes tier→feature). Entitlement-source resolution mirrors the rate-limit middleware
  (provider's engine → wired store → none): **no source** = dedicated single-kernel deploy, not
  tier-limited (tier `null`, every feature on); **source present but unprovisioned/suspended** =
  fail-closed (`NO_ACTIVE_PLAN`, every feature off). Bearer required (401 otherwise); API-key
  protected when `require_api_key=True` (any valid tenant key reads its own tier). New
  `EntitlementsResponse` schema; router wired into `create_app`. **Frontend (`console/`, still
  dependency-free):** `src/oidc/` — PKCE helpers over Web Crypto (`pkce.ts`: S256 challenge, random
  verifier/state, unverified JWT-claim decode), env-driven config (`config.ts`,
  `VITE_OIDC_*`), and the flow (`oidc.ts`: discovery via `/.well-known/openid-configuration` or
  pinned endpoints → redirect → `/callback` code exchange → store the **id_token as the session
  bearer** + tenant from its claim). The kernel's OIDC IdentityPort still **cryptographically
  verifies** that token (issuer/audience/JWKS) — the console only reads the tenant claim to scope its
  calls (selection ≠ authorization). New `pages/Callback.tsx`, `state/entitlements.tsx`
  (context provider fetching `/v1/me/entitlements` once post-auth + `useFeature` hook), `clearSession`
  logout, tier badge, and nav/route gating (`FeatureGate` hides Policies/Approvals on tiers that lack
  them). Token-paste remains as a documented dev fallback when `VITE_OIDC_*` is unset; `.env.example`
  added. `npm run build` (tsc strict + vite) green. **Tests:** +8 (`test_entitlements.py` — 401,
  no-source-unlimited, STARTER/BUSINESS/ENTERPRISE feature derivation, fail-closed unprovisioned +
  suspended, provider-mode tenant resolution); suite 827 → **835**. **Follow-ups:** OIDC end-to-end
  requires the kernel deployed with `identity = "oidc"` and `audience = VITE_OIDC_CLIENT_ID` (the
  backend connectors landed in the prior WS-D entry); silent token refresh / `prompt=none` renewal
  (the console currently re-logs in when the id_token expires); model-registry (K·08) / consent
  (K·04) / tenant-config console surfaces remain unbuilt.

- **2026-06-13 · WS-E Enterprise isolation hardening — schema-per-tenant + RLS · adapters/storage** —
  Hardened tenant isolation from *logical* (every row carries `tenant_id`, every query predicates on
  it) to *physical* for the dedicated Enterprise tier, per F-07. New `adapters/storage/isolation.py`:
  the mechanism — `assert_safe_tenant`/`safe_schema_name` derive a tenant's physical schema name and
  are **fail-closed** (a tenant id that isn't a bare `[a-z0-9_-]` identifier raises
  `TenantIsolationError` rather than being escaped into SQL — a crafted id can never become SQL);
  `search_path_sql` pins a connection to the tenant's schema; `set_rls_tenant_sql` is a **parameterized**
  `set_config('app.current_tenant', $1, true)` (tenant id is always a bind param); `current_db_tenant`
  ContextVar + `db_tenant_scope` carry the RLS tenant per transaction. New
  `adapters/storage/provisioner.py` — `TenantProvisioner.onboard/offboard` create/drop a tenant's
  isolated schema with its own copy of every kernel table (`onboard_statements` runs CREATE SCHEMA →
  pin search_path → CREATE TABLE so the tables land in the tenant schema, not `public`); fail-closed
  wrapping. New Alembic migration `004_enable_rls.py` — enables + **forces** RLS on the three shared
  kernel tables with a deny-by-default policy keyed on `current_setting('app.current_tenant')` (belt
  and braces over the schema isolation). Exposed from `adapters.storage`. **Tests:** +21
  (`test_tenant_isolation.py` — schema derivation, 7 injection/oversize tenant ids rejected, SQL
  builder shapes, RLS-param-bound assertion, ContextVar set/restore + nested, onboard/offboard
  statement order, and provisioner execution over a mocked asyncpg pool incl. fail-closed + unsafe
  tenant); suite 806 → **827**. The live schema-per-tenant query path is exercised by the
  `DATABASE_URL`-gated integration suite (the SQL generation + guards are fully unit-covered here).
  **Follow-ups:** wire the Postgres adapters to issue `search_path_sql` + `set_rls_tenant_sql` per
  transaction when an Enterprise `rls=True` flag is set; run the migration set against each onboarded
  schema (currently the provisioner ships the table DDL inline).

- **2026-06-13 · WS-G GDPR/DPDP crypto-shredding erasure · core/erasure · delivery** —
  Built right-to-erasure for a system whose audit log is **append-only and tamper-evident** — you
  cannot delete a sealed K·02 entry without invalidating every downstream Merkle proof. Erasure is
  therefore cryptographic: PII is stored as AES-256-GCM ciphertext under a **per-subject** key, and
  "delete" = **destroy the key** (crypto-shredding) → the ciphertext is permanently irrecoverable
  while the Merkle leaves (computed over the ciphertext token) stay byte-identical, so the trail's
  integrity survives the deletion. New `core/erasure/`: `ShredKeyring` /
  `InMemoryShredKeyring` (per-`(tenant, subject)` DEK, thread-safe, **tombstones** erased subjects —
  no resurrection, F-07 tenant-scoped); `ErasureEngine` — `encrypt`/`decrypt` over a self-describing
  `CipherToken` (AEAD; tamper → `CipherTokenError`), `erase` returning an `ErasureReceipt` (ledger-
  sealable proof the right was honored), `is_erased`. Once shredded, `decrypt` raises
  `SubjectErasedError` (the *intended* terminal state). New error subtree in the frozen
  `core/errors.py` (`ErasureError`, `SubjectErasedError`, `CipherTokenError`); new
  `erasure:write` RBAC scope. New routes `POST /v1/erasure/{tenant}/{subject}` (crypto-shred) +
  `GET /v1/erasure/{tenant}/{subject}` (status) — bearer + tenant-isolation + scope guarded;
  `create_app(erasure_engine=…)` wires it, and a `SubjectErasedError` handler returns **410 Gone**.
  **Tests:** +19 (engine: round-trip, key reuse/isolation, erase→irrecoverable, idempotent,
  no-resurrection, cross-subject + cross-tenant isolation, tamper/malformed fail-closed, **and the
  WS-G invariant — a Merkle leaf over the cipher token is unchanged after erasure**; routes:
  erase→status, pre-erase false, 401 no-token, 403 cross-tenant, 503 disabled, 410 on decrypt-after-
  erase); suite 787 → **806**. **Follow-ups:** HSM/KMS-backed keyring (DEK never leaves the HSM;
  destroy = KMS key-destruction API) behind the same `ShredKeyring` interface; durable keyring +
  hydrate; seal the `ErasureReceipt` into the ledger as an erasure-evidence action.

- **2026-06-13 · WS-F regulator ledger-proof export · core/regmap · core/ledger · delivery** —
  Turned the K·14 evidence pack (which took *opaque* proof-ref strings) into a **self-contained,
  independently verifiable** regulator export over the real K·02 transparency log. New
  `core/regmap/export.py`: `build_ledger_proof_bundle` assembles, for a tenant + time window, a
  `LedgerProofBundle` = the signed tree head (RFC 6962 STH: size, root, Ed25519 signature, **+ the
  signing public key**) + one RFC 6962 inclusion proof per in-window action (leaf hash + audit path)
  + the K·14 evidence narrative/manifest with *real* leaf-hash proof refs. Shipped alongside is
  `verify_ledger_proof_bundle(dict) -> (ok, errors)` — the exact offline check a regulator runs: it
  recomputes the Merkle root from each inclusion proof (`_recompute_root_from_path`) and asserts it
  equals the **signed** root, then verifies the STH signature against the embedded public key. Tamper
  anywhere (leaf, root, signature) → verification fails; a bundle with no public key is flagged
  unverifiable. `InMemoryEd25519Signer` gained a `public_key_pem` property (SPKI PEM) so the export is
  verifiable end-to-end (the OpenBao signer can expose the same — follow-up). New SDK method
  `Kernel.export_ledger_proof(tenant, window_start=, window_end=, regulation_refs=, policy_versions=)`
  (reads only sealed entries — no model re-calls, F-09; window-filters by `sealed_at`). New routes
  `GET /v1/ledger/{tenant}/export` (same bearer + `ledger:read` scope + tenant-isolation guard as the
  trail; ISO `from`/`to` + `regulations`/`policy_versions` query params) and `POST
  /v1/ledger/export/verify` (stateless mirror of the offline verifier). **Tests:** +13
  (`test_export.py` clean/single/tamper-leaf/tamper-sig/tamper-root/missing-key/malformed;
  `test_ledger_export.py` export→verify round-trip, 401 no-token, 403 cross-tenant, tampered-bundle
  rejected, window filter); suite 775 → **787**. **Follow-ups:** expose `public_key_pem` from the
  OpenBao signer so production exports are offline-verifiable; consistency-proof export across two
  STHs for append-only continuity attestation.

- **2026-06-13 · WS-C billing → tier flips + usage metering · core/billing · core/metering · delivery** —
  Turned the entitlement plumbing (which already carried `billing_provider`/`billing_ref` and a
  `SUSPENDED` status) into a working billing edge. **Provider-agnostic core:** new `core/billing/`
  — `BillingEvent`/`BillingEventType` (the normalized vocabulary: SUBSCRIPTION_ACTIVE,
  PAYMENT_FAILED, PAYMENT_RECOVERED, SUBSCRIPTION_CANCELLED, IGNORED), `BillingPort`
  (`verify_and_parse(payload, headers) -> BillingEvent` — signature-verify + normalize, fail-closed),
  and `BillingEngine` which maps a verified event onto the existing fail-closed store mutations
  (active → set tier + ACTIVE + stamp provider/ref; payment-failed → SUSPEND; recovered →
  reactivate; cancelled → downgrade to free STARTER; unknown-tenant non-active events are no-ops;
  idempotent). **Adapters:** `adapters/billing/stripe.py` (verifies the `Stripe-Signature` HMAC over
  `"{t}.{body}"` within a timestamp tolerance; maps `customer.subscription.*` / `invoice.payment_failed`;
  price→tier) and `adapters/billing/razorpay.py` (verifies the `X-Razorpay-Signature` body HMAC; maps
  `subscription.activated/charged/halted/cancelled`; plan→tier) — **no Stripe/Razorpay SDK**, plain
  `hmac`/`hashlib`/`json` so the verification path is auditable + testable. **Route:** `POST
  /v1/billing/webhook/{provider}` reads the **raw** body (signature is over exact bytes), verifies +
  applies; bad signature → 400 (no plan change), unmappable-but-verified → 422, provider not wired →
  503. Webhooks are exempt from API-key auth (provider signature is the credential) and from rate
  limiting. **Usage metering:** new `core/metering/UsageMeter` (per-tenant, per-UTC-day counter,
  auto-rollover); `RequestLoggingMiddleware` records one tick per successful governed `/v1` request
  (best-effort, never affects the response); `RateLimitMiddleware` now also enforces the tier's
  `max_actions_per_day` (429 `QUOTA_EXCEEDED`, fail-open without a meter/plan); new admin route
  `GET /v1/admin/tenants/{tenant}/usage`. `create_app` gained `billing_adapters` / `billing_engine` /
  `usage_meter`. New `BillingError` subtree in the frozen `core/errors.py`
  (`WebhookVerificationError`, `BillingEventError`). **Tests:** +38 (billing engine, Stripe + Razorpay
  signature/parse incl. tamper/stale/wrong-secret/unmapped, usage meter, webhook route incl. flip /
  bad-sig-no-flip / auth-exempt, metering on success, admin usage, daily-quota 429); suite 737 →
  **775**. **Follow-ups:** distributed (Redis) usage counter for horizontal scale; emit a K·07 event on
  tier flips so the audit trail records billing-driven plan changes; checkout-session creation
  endpoints (the kernel currently only consumes provider webhooks).

- **2026-06-13 · WS-D named IdP connectors — OIDC discovery + JWKS rotation · adapters/identity** —
  Built the remaining WS-D slice: verify IdP-issued (asymmetric) JWTs against a named provider's
  rotating JWKS, layered on the existing JWT claim mapping. New `adapters/identity/_claims.py`
  (`actor_from_claims` — the shared, single-source claim→`Actor` mapper incl. the F-07 tenant
  cross-check; `JWTIdentityAdapter` now delegates to it so the two adapters cannot drift). New
  `adapters/identity/oidc.py` — `OIDCIdentityAdapter`: (1) OIDC **discovery** from
  `{issuer}/.well-known/openid-configuration` when no `jwks_uri` is given, (2) JWKS fetch + `kid`
  index cached for `jwks_ttl`, (3) **rotation** — an unknown `kid` triggers exactly one re-fetch,
  still-missing → fail-closed, (4) `jwt.decode` with mandatory `issuer` + `audience` checks and
  `require=[exp,iss,aud]`. Provider presets `OIDCIdentityAdapter.okta/auth0/keycloak` (issuer-URL
  shaping only; Auth0's trailing slash preserved). HTTP fetch is injectable (`jwks_fetcher=`) so the
  adapter is fully testable without a live IdP. Registered `oidc` in the kernel adapter registry
  (`_build_identity` already reads `[identity]` kwargs → wireable via `identity = "oidc"`); documented
  in `kernel.example.toml`. **Tests:** +16 (`test_oidc_identity.py` — valid/aud/iss/expiry/unknown-key/
  unknown-kid/no-kid, tenant-mismatch isolation, rotation refetch + TTL cache hit, the three provider
  presets), all 11 JWT-adapter tests unchanged after the refactor; suite 720 → **737**. **Follow-ups:**
  console OIDC login + per-tier UI gating (the last Wave-2 slice; frontend); distributed JWKS cache if
  the kernel is horizontally scaled (currently per-process).

- **2026-06-13 · WS-D auth/metering edge — API-key auth, RBAC scopes, rate limiting, request logging · core/delivery (ADR-0011)** —
  Closed the unguarded edge left by ADR-0009/0010. **RBAC scopes:** new `core/account/scopes.py`
  (`"resource:verb"` constants + fail-closed `normalize_scopes`); `ApiKey` now carries a
  `frozenset` of scopes (signup key = `OWNER_SCOPES`, all), `issue_api_key(tenant, scopes=…)` mints
  least-privilege keys, and `AccountEngine.resolve_principal` returns an `AuthenticatedPrincipal`
  (tenant/account/key id/scopes) while `verify_api_key` keeps its `Account` return for compatibility.
  **API-key auth:** new `delivery/api/auth.py` — `ApiKeyAuthMiddleware` (opt-in via
  `create_app(require_api_key=True)`) requires a valid `qk_` key on protected `/v1/*` paths
  (`/v1/signup` + admin-token-guarded `/v1/admin/*` exempt), verifies it, binds the key's tenant to the
  request's routing tenant (403 `TENANT_ISOLATION` on mismatch), and stashes the principal.
  `enforce_scope(request, scope)` is wired into every per-tenant route (`actions:write/read`,
  `ledger:read`, `dashboard:read`, `approval:read/decide`, `inference:write`, `policy:admin`) and is a
  **no-op when auth is disabled**, so IdP-token/single-kernel deployments and the existing suite are
  untouched. **Rate limiting:** new `delivery/api/ratelimit.py` — `RateLimitMiddleware` enforces
  `EntitlementEngine.rate_limit_for(tenant)` (tier default from `TIER_MATRIX`, honoring
  `quota_overrides`) over a fixed 1-minute window → **429 + Retry-After**; fails open when no
  entitlement source / unresolved tenant / unbounded tier. **Observability:** new
  `delivery/api/observability.py` — `RequestLoggingMiddleware` (always on) assigns/propagates
  `X-Request-ID` and emits a structured access log (method, path, status, duration, tenant) — the
  substrate WS-C metering/billing builds on. `create_app` gained `require_api_key` (default off) and
  `rate_limit` (default on, no-op without entitlements); middleware order is
  CORS → RequestLogging → RateLimit → ApiKeyAuth → reference PEP → routes. ADR-0011. **Tests:** +16
  (scopes, API-key auth incl. tenant-mismatch/revoked/insufficient-scope/signup-exempt, rate-limit
  429 + exempt + fail-open, request-id propagation); suite 704 → **720**, all prior API tests
  unchanged. **Follow-ups:** remaining WS-D slice = named IdP connectors (OIDC/JWKS) + console OIDC,
  moved to Wave 2; distributed (Redis) rate-limit store when horizontal scale needs a shared counter.

- **2026-06-13 · Commercial tiering + provisioning + shared-plane routing · core/delivery (ADR-0009, ADR-0010)** —
  Started the productization program: turn the feature-complete engine into a sellable 3-tier product
  (STARTER / BUSINESS / ENTERPRISE) from one codebase. **Wave 0 — entitlement/tiering foundation:**
  new `core/entitlements/` (`FeatureTier`, immutable `CustomerPlan`, and `TIER_MATRIX` — the single
  source of truth mapping each tier to its allowed adapters, governance-profile presets, and quotas;
  `EntitlementEngine` is a fail-closed query layer over an `EntitlementStore` with durable
  write-through + `hydrate()`, mirroring `core/policy`). New `core/license/` — offline Ed25519-verified
  Enterprise `License` (same `cryptography` primitives as the ledger signer), fail-closed on
  missing/expired/forged tokens. New `delivery/sdk/provider.py` — `TieredKernelProvider` pre-builds one
  STARTER and one BUSINESS kernel and routes each request to its tier's kernel (`for_saas`); the
  ENTERPRISE path (`for_enterprise`) refuses to boot without a valid license. Isolation between
  Starter and Business is **structural** — a Starter request lands on a kernel physically lacking the
  CEL/Postgres adapters, not a runtime flag. ADR-0009. **Wave 1 — provisioning + API integration:**
  new `core/account/` (`AccountEngine.signup` → mints a tenant, provisions a default STARTER plan, and
  issues one hashed API key; `verify_api_key` is the fail-closed self-serve auth path). `create_app`
  now takes `kernel=` **or** `provider=` plus control-plane singletons; new `delivery/api/deps.py`
  (`get_kernel` / `get_request_tenant`) resolves the serving kernel + tenant in both single-kernel and
  shared-plane modes — routing reads the (unverified) JWT tenant claim only to *select* the kernel,
  which then cryptographically verifies the token (selection ≠ authorization). New routes
  `/v1/signup` (the one intentionally open onboarding write) and `/v1/admin/tenants*` (admin-token
  guarded; set-tier flips a tenant's plan). The SDK's `resolve_actor`/`check`/`generate` gained a
  per-request `tenant` param (defaulting to the kernel's own), and **all** per-tenant routes
  (`actions`, `authorize`, `inference`, `ledger`, `dashboard`, `approvals`, `policies`) were migrated
  to the resolver so a shared tier-kernel scopes identity/data/isolation to the request's tenant, not
  its fixed one. New error subtrees in the frozen `core/errors.py` (`EntitlementError`, `LicenseError`,
  `AccountError`). ADR-0010. **Tests:** +46 (entitlements engine/store/license, account engine,
  signup/admin routes, and provider-mode E2E routing incl. structural isolation + cross-tenant 403);
  suite 658 → **704**, the 105 existing single-kernel API tests unchanged. **Follow-ups (next waves):**
  WS-D auth/metering edge (rate limits from `TIER_MATRIX`, request/usage logging, API-key auth on
  protected routes, RBAC scopes, named IdP connectors); WS-C Stripe + Razorpay billing → tier flips;
  WS-F regulator proof export; WS-E Enterprise isolation hardening; WS-G GDPR crypto-shredding.

- **2026-06-12 · Operator console + HITL approvals API · delivery/console** — Gave deployed clients a
  UI to run the kernel. **Backend:** new `delivery/api/routes/approvals.py` (`GET /v1/approvals`,
  `POST /v1/approvals/{id}/{approve,reject}`) over the in-process HITL port — token-resolved actor,
  the port enforces approver eligibility + the self-approval guard; supported by
  `ApprovalStore.list_pending`, `InProcessHITLPort.list_pending`, `Kernel.list_pending_approvals` /
  `decide_approval`, and approval response schemas. `create_app` now mounts `CORSMiddleware`
  (configurable `cors_origins`, default the Vite dev origin) so a separate console origin can call
  the API. 11 new backend tests; suite 647 → **658**. **Frontend:** new `console/` — a plain
  React + Vite + TypeScript app (no design system, per scope) with four areas: **Dashboard**
  (overview, decision timeline, top actions, HITL depth), **Policies** (register → submit →
  **simulate/backtest** → acknowledge-&-activate → deprecate), **Audit trail** (sealed ledger
  entries), **Approvals** (pending queue + approve/reject). Typed `fetch` client over the existing
  `/v1` API, token-paste auth (the kernel consumes tokens; the console doesn't mint them), dev proxy
  to `:8000`. `npm run build` (tsc strict + vite) is green. **Caveat:** the approvals queue is the
  operator surface over the in-process store; wiring an approval to *resume* a suspended action needs
  the async K·06 process-engine deployment (the synchronous lifecycle times a gate out immediately).
  **Follow-ups:** login/OIDC instead of token-paste; model-registry (K·08) + consent (K·04) config
  surfaces; richer charts.

- **2026-06-12 · Durable ledger persistence · ledger/adapters/delivery (ADR-0008)** — Closed the
  heaviest pre-sale blocker: the K·02 transparency log survived only in process memory (lost on
  restart) behind the durable OpenBao *signing key*. Mirroring ADR-0005's write-through policy store:
  new async `LedgerRepository` port (`core/ledger/repository.py`) + `LedgerPersistenceError`;
  `InMemoryLedgerRepository` (default/tests) + `PostgresLedgerRepository` (asyncpg, mock-tested) +
  Alembic migration `003` (`quaicu_ledger_entries` keyed `(tenant_id, ledger_seq)`,
  `quaicu_ledger_sth` keyed `tenant_id`). `TrustLedger` gains an optional `repository`: `seal()` is
  write-through (append leaf → sign head → persist entry + STH **before** committing in-memory; on
  any failure `MerkleTree.pop_last` rolls back and the action HALTs fail-closed), and `hydrate()`
  rebuilds every tenant's tree from the stored leaf hashes (`append_leaf_hash`), restoring entries,
  sequence, and the signed head. `OpenBaoLedgerAdapter` takes an optional `repository` + `hydrate`;
  the kernel wires `[adapters].ledger_store` via `_build_ledger`, exposes `kernel.ledger_repository`,
  hydrates the ledger in `startup()`, and closes it in `shutdown()`. Proofs stay on the fast
  in-memory path (no DB round-trip). 20 new tests (merkle rehydrate/pop, write-through + hydrate
  round-trip + tenant isolation + fail-closed rollback, mock Postgres adapter, kernel startup
  hydrate) + a `DATABASE_URL`-gated Postgres round-trip; suite 627 → **647** (10 skipped on a bare
  checkout). **Follow-ups:** physical per-tenant ledger tables + the K·02 crypto review remain.

- **2026-06-12 · Capture the approving identity in the ledger · hitl/lifecycle (ADR-0007)** — Closed
  the "who approved this?" audit gap. The lifecycle sealed `approver=None` because `HITLPort.poll`
  returned a bare `ApprovalDecision` and never reported the decider (captured one layer down in
  `ApprovalRecord.decided_by`). **ADR-0007** enriches the frozen port: new `ApprovalOutcome(decision,
  decided_by)` (`core/types.py`); `HITLPort.poll -> ApprovalOutcome`; `InProcessHITLPort` returns
  `record.decided_by`, the webhook adapter reads a `decided_by` body field. The lifecycle's `_gate`
  now seals the decider as `ApproverRef("user:<id>")` into `LedgerEntry.approver` (a backend that
  approves without an identity seals `None`); `_poll_until_decided` returns the full outcome.
  Fail-closed unchanged (REJECTED/TIMED_OUT still deny). The approver was already inside the Merkle
  leaf (`_canonical_bytes`) and is surfaced by `GET /v1/ledger/{tenant}/trail`, so the gap closes
  end-to-end with no read-side change. Updated the 3 `poll` implementers + the HITL/lifecycle poll
  assertions; added sealed-approver tests (with and without a reported decider). Suite 626 → **627**.

- **2026-06-12 · Seal `actor_roles` for role-based backtest replay · ledger/sandbox/policy (ADR-0006)** —
  Closes the simulate backtest's last fidelity gap. The `/simulate` candidate evaluator could replay
  `actor_id` conditions (id was already sealed) but **not** `actor_roles` — roles weren't on the
  `LedgerEntry`, so role-gated conditions (`"role:risk_head" in actor_roles`, the common shape) hit
  an undefined CEL var, raised, and scored fail-closed `deny`, overstating flips. **ADR-0006** adds
  `actor_roles: tuple[str, ...] = ()` to the frozen `LedgerEntry` (extending the contract surface
  under ADR-0001's incremental-freeze rule): `seal()` populates it from `action.actor.roles` and
  `_canonical_bytes` commits it to the Merkle leaf next to `actor_id` (tamper-evident, F-09). The
  K·13 `CandidateEvaluator` contract grew a 5th `actor_roles` arg; `run_counterfactual_backtest`
  passes `entry.actor_roles`; the route's `_cel_activation` sets the CEL `actor_roles` list var
  (mirroring the live `_build_activation`). Role-based policies now replay faithfully. 1 new ledger
  test (`test_seal_records_actor_roles`) + the simulate roles test flipped to assert faithful eval;
  suite 625 → **626**. **No remaining actor field is unsealed** — the simulate-fidelity follow-up is
  fully closed.

- **2026-06-11 · Backtest→ImpactReport simulate bridge + dashboard read-models · sandbox/policy/delivery** —
  Closes the last two pre-management-API gaps (#4 + #5). **Gap #4 (F-10 bridge):** new pure
  `core/sandbox/bridge.assemble_impact_report(SandboxRun, *, reviewed_by, fairness_delta=None,
  acknowledged=False)` converts a K·13 counterfactual run (+ optional K·09 `FairnessDelta`) into the
  K·01 `ImpactReport` the activation gate consumes — `decision_distribution` is a conservative
  two-bucket proxy (unchanged→allow, flipped→deny), `flip_count`/`fairness_delta` carried through,
  `acknowledged` defaults False (a reviewer must still acknowledge before activation). New route
  `POST /v1/policies/{id}/versions/{v}/simulate` (REVIEW-only, 409 otherwise): re-evaluates the
  candidate version's compiled CEL against the tenant's sealed `LedgerEntry` set via
  `run_counterfactual_backtest` (no model re-calls, F-09), optionally runs a fairness sweep when
  `group_key` is given, assembles the report, and persists it when `auto_store=True`. The candidate
  evaluator is fail-closed — a missing program or any CEL fault scores the entry `deny`. The recorded
  `actor_id` is threaded through the backtest (the K·13 `CandidateEvaluator` contract was widened to
  pass `LedgerEntry.actor_id`), so `actor_id`-based conditions replay faithfully. (At the time, actor
  `roles` were not carried on the entry, so `actor_roles` conditions re-evaluated fail-closed — now
  closed by ADR-0006, see the top Log entry.) **Gap #5 (dashboards):** new `delivery/api/routes/dashboard.py` with four
  read-only, tenant-isolated (401/403) projections over `ledger.get_entries`: `/overview` (decision
  counts + denial rate + last seq), `/decisions` (per-day buckets over a window), `/actions/top`
  (volume + denial rankings), `/hitl/queue` (pending depth). Supporting surface:
  `ApprovalStore.pending_count()` + `Kernel.hitl_queue_depth` (in-process adapter only; external
  queues report 0). 36 new tests (`test_bridge.py`, `test_simulate.py`, `test_dashboard.py`); suite
  586 → **622** (631 with live deps). **Follow-ups:** dashboard projections are full-scans (fine for
  MVP; a materialized read-model replaces them at volume); approver-identity capture + K·02 external
  crypto review + durable ledger persistence remain open (see above).

- **2026-06-11 · Integration-environment validation + OpenBao sign fix · adapters/infra** (commits
  `00b77581`, `5d1edb26`) — Stood up the real external dependencies and ran the integration suites
  that had only ever been skipped. **Postgres:** provisioned a GCP Cloud SQL instance
  (`quaicu-pg`, POSTGRES_16, project `ordinal-quarter-499114-s2`), connected via the Cloud SQL Auth
  Proxy on `localhost:5433` (keyless ADC — org policy blocks downloadable SA keys), ran Alembic
  migrations, and turned the 5 storage conformance tests green. **OpenBao:** ran `openbao/openbao`
  dev in Docker, enabled Transit + an `ed25519` `quaicu-ledger` key, and turned the 4 ledger
  conformance tests green. **Bug found + fixed:** `adapters/ledger/openbao.py` was sending
  `hash_algorithm="none"` on `transit/sign`, which current OpenBao rejects with 400 (it routes that
  into an RSA-only prehash validation path — *"requires prehashed=true and signature_algorithm"*).
  Ed25519 signs the raw message, so the param is now omitted; this would have broken production
  signing against any recent OpenBao. Unit test `test_openbao_signer.py::test_sign_sends_correct_payload`
  updated to assert its absence. **With both deps live: 595 passing, 0 skipped.** **Detour (reverted):**
  briefly built a Cloud KMS ECDSA-P256 `TreeSigner` (`cloudkms_ledger`) as a GCP-native alternative —
  owner chose to keep OpenBao (Ed25519, portable / on-prem / air-gapped), so the adapter + ADR 0006 +
  KMS tests were removed and the KMS key scheduled for destruction. OpenBao remains the sole production
  signer; `.tools/` (proxy binary) and `graphify-out/` gitignored.

- **2026-06-11 · Policy Management HTTP API + control-plane authz · policy/delivery** — Closes
  pre-management-API gaps #3 (no policy CRUD surface) + #6 (no control-plane authz). New route module
  `delivery/api/routes/policies.py` exposes eight endpoints under `/v1/policies`: `POST` register (DRAFT),
  `GET` list (`?lifecycle=` filter), `GET /{id}` versions, `GET /{id}/versions/{v}`, `POST .../submit`
  (DRAFT→REVIEW), `PUT .../impact-report` (store an F-10 report), `POST .../activate` (REVIEW→ACTIVATED,
  F-10 gate, inline or stored report), `POST .../deprecate`. All are thin adapters over the SDK
  write-through primitives. **Authz:** every endpoint (reads included) resolves the actor from the
  bearer token via the IdentityPort and requires a policy-admin role — route-level, **not** governed
  actions, to avoid the empty-store bootstrap deadlock (a fail-closed store could never register its
  first policy). Roles are configurable via `[governance] policy_admin_roles` (bare / `role:`-prefixed
  forms interoperate, normalised to the HITL convention). **Supporting surface:** `PolicyTransitionError`
  (`POLICY_TRANSITION_INVALID`); `PolicyStore` management API — an `_assert_registrable` immutability
  guard (ACTIVATED/DEPRECATED versions cannot be re-registered; runs *before* the durable write in
  `register_persisted`), reads (`get` / `list_policies` / `list_versions` / `get_impact_report`),
  `submit_for_review(_persisted)`, `store_impact_report_persisted`; `LifecycleEngine.identity` property;
  `Kernel.resolve_actor` + `submit_policy_for_review` / `store_policy_impact_report` passthroughs +
  `policy_admin_roles` field & config plumbing. Error mapping: bad CEL → 400, lifecycle/F-10 violations
  → 409, persistence fault → 503 (via the global handler), unknown id/version → 404 (route pre-check).
  54 new tests (`test_policies.py`, `test_store_management.py`, extended `test_policy_wiring.py`) —
  auth, role normalization both directions, the full HTTP lifecycle journey, persistence fail-closed,
  and hydrate-after-restart; suite 532 → **586**. **Follow-ups:** gaps #4 (backtest→ImpactReport
  bridge) / #5 (dashboard read-models) remain.

- **2026-06-10 · CEL engine config-wired + durable policy store · policy/delivery** (commit
  `e121a9fe`, ADR-0005) — Closes pre-management-API gaps #1+#2. New `PolicyRepository` async port
  (`core/policy/repository.py`) + `PolicyPersistenceError`; `InMemoryPolicyRepository` (default) and
  `PostgresPolicyRepository` (asyncpg upsert, mock-tested) + Alembic migration `002` (`quaicu_policies`
  + `quaicu_policy_impact_reports`). `PolicyStore` gains an optional repository and write-through async
  methods — `hydrate()` (recompiles CEL on load; compiled programs are never persisted),
  `register_persisted` / `activate_persisted` / `deprecate_persisted` — while the sync `register` /
  `activate` / `lookup` API and the 22 existing K·01 tests stay untouched. `Kernel` wires
  `policy = "cel_policy"` via `_build_policy` (with `[adapters].policy_store` selecting
  `memory_policy` / `postgres_policy`), exposes `policy_store` / `policy_repository`, adds
  `startup()` / `shutdown()` (hydrate on boot; wired into the FastAPI lifespan), and ships the SDK
  write-through primitives `register_policy` / `activate_policy` / `deprecate_policy` (the surface the
  management API will wrap). **No file seeding** — an empty store fail-closed DENYs until policies are
  written and ACTIVATED (secure default, F-10). 26 new tests; suite 506 → **532**. **Follow-ups:**
  gaps #3 (CRUD routes) / #4 (backtest→ImpactReport bridge) / #5 (dashboard read-models) remain.

- **2026-06-10 · Pre-management-API gap audit · orchestrator** — Audit before planning the Policy
  Management API + dashboards. **Gaps found (must close first):**
  1. **CEL engine not wired to config.** `Kernel._ADAPTER_REGISTRY` registers only `always_allow`
     for the `PolicyEvaluator` slot. The real `core/policy/PolicyEngine`+`PolicyStore` can only be
     injected via `from_parts` in code — `from_config` cannot select it. A management API is
     meaningless until config can wire the CEL engine. **Fix:** register `cel_policy` →
     `(PolicyEngine over PolicyStore)`; expose the store to the API layer.
  2. **No policy persistence.** `PolicyStore` is in-memory + `threading.Lock`; restart loses all
     policies. `adapters/policy/` has only `always_allow`. **Fix:** a Postgres-backed policy store
     (mirror the K·02/storage adapter pattern) or the API will write to volatile memory.
  3. **No policy CRUD surface.** `delivery/api/routes/` has actions/authorize/inference/ledger but
     no `/v1/policies`. Need register / list / get / activate / deprecate, all authz-gated.
  4. **F-10 activation gate has no ImpactReport producer.** `PolicyStore.activate` requires an
     acknowledged `ImpactReport` (decision_distribution, flip_count, **fairness_delta**), but K·13
     `run_counterfactual_backtest` returns a `SandboxRun` (flip_rate, counts) — nobody converts
     SandboxRun (+ K·09 fairness) into an ImpactReport. Without this bridge, activation is either
     blocked or bypassed. **Fix:** a backtest→ImpactReport assembler + a `/v1/policies/{id}/simulate`
     route over the ledger entries.
  5. **No dashboard read-models.** Dashboards need aggregates (decision counts, denial rate over
     time, top-denied action types, HITL queue depth, policy hit counts, drift/fairness status). The
     ledger exposes only `get_entries(tenant)` (full scan); events are in-memory only — no query/
     aggregation API and no durable event sink. **Fix:** a read-model/projection layer + query routes.
  6. **No authz for the control plane itself.** Who may author/activate/deprecate a policy? Needs an
     RBAC check on the management routes (a policy governs the policy API — dogfood the kernel).
  **Exposes** the dependency-ordered plan: wire CEL engine → policy persistence → CRUD routes →
  backtest/ImpactReport bridge → read-models → dashboards. No code changed in this entry.

- **2026-06-10 · Zero-friction integration · delivery** (commit `590e2073`) — Added integration
  primitives so an existing codebase adopts governance by *adding lines only* — no function-signature
  or call-site changes. `core/lifecycle/context.py` (actor `ContextVar`, task-local; `actor_scope`
  /`async_actor_scope`); `kernel.actor_context(actor)` (bind identity once per request/session);
  `@kernel.guard(policy=...)` (decorate any existing fn, signature unchanged, actor from ContextVar);
  `kernel.wrap(fn, policy=...)` (programmatic form for third-party callables); `kernel.proxy(obj,
  policies={...})` (`delivery/sdk/proxy.py` — transparent object proxy governing only listed dotted
  method paths, all other attribute access passes through). 20 new tests; suite 486 → **506**.

- **2026-06-10 · Decision-only authorize + monitor + reference PEP · lifecycle/delivery** (commit
  `66f49319`) — Split decision from execution (PDP/PEP). `core/lifecycle/decision.py`
  (`AuthorizationResult`); `LifecycleEngine.decide()` (side-effect-free verdict — no insert, no state
  transition, no emit; best-effort monitoring seal); `_consent_verdict()` (non-mutating consent check
  shared by `run`+`decide`); `GovernanceProfile.monitor()` preset; `kernel.check()` /
  `BoundAgent.check()` (never raise on DENY — caller is the PEP); `POST /v1/authorize` (pure PDP,
  always 200, verdict in body); `delivery/api/middleware.py` (`GovernanceMiddleware`, opt-in via
  `create_app(enforce_paths=...)`). Under the default `all()` profile every decision is sealed to the
  ledger (tamper-evident monitoring). 40 new tests; suite 446 → 486.

- **2026-06-10 · Security hardening + composable governance · multiple** (commit `5dc7ca75`) —
  Two efforts. **(a) 8 security/fail-closed fixes** from a full-codebase review: REST API requires a
  bearer token (actor from token, never body); ledger trail route + cross-tenant 403 + `get_entries`;
  real pattern-based PII masking (PAN/Aadhaar/email/phone/SSN/CC) replacing a no-op stub; consent
  fail-open fixed (non-active → DENY); HITL role-based approver authz + self-approval guard; storage
  failures HALT instead of escaping `run()`; identity resolved before idempotency insert (no poisoned
  slot); Merkle leaf now commits payload + non-dict result. **(b) Composable governance + agent
  integration:** `GovernanceProfile` (`core/lifecycle/profile.py` — per-call layer toggles + presets
  all/standard/gateway_only/audit_only; engine `run(profile=)` honors each layer + a standalone
  consent step; enforced layers sealed into the leaf); AI Gateway wired into the Kernel
  (`kernel.generate()`, `POST /v1/inference`, `[gateway]`/`[governance]` config); `kernel.governed_tool()`
  + `kernel.for_agent()` → `BoundAgent` (per-agent identity in the ledger). Suite 402 → 446.

- **2026-06-08/09 · Production adapters + CI/CD · delivery** (commits `cb2b956f`, `7075e9cb`,
  `fb6fbc34`) — `adapters/storage/postgres.py` + Alembic migrations (StoragePort); OpenBao signer
  adapter for durable Ed25519 STH signing (K·02); GitHub Actions CI + signed Docker release pipeline
  (cosign keyless). Suite reached 402. **Follow-up:** ledger tree/entries still in-memory behind the
  OpenBao signer; external crypto review still outstanding.

- **2026-06-07 · All 14 layers + delivery complete (Waves 3–5) · multiple** (commit `648be5a2`) —
  Completed K·04 Consent, K·06 Process, K·08 Registry, K·09 Fairness, K·10 Drift, K·11 Explainability,
  K·12 Incident, K·13 Sandbox (`run_counterfactual_backtest`), K·14 Regulatory Mapping
  (`RegulationCatalog` + `generate_evidence_pack`), plus the adapters (inference/hitl/storage/identity/
  workflow) and the delivery phase (SDK `Kernel`, FastAPI app + routes, Dockerfile/Helm). This is the
  point the work-queue table above transitioned almost entirely to **done**.

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
