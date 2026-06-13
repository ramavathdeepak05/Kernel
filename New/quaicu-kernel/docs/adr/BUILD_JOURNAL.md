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

## Current status (2026-06-13)

**All 14 governance layers + the delivery phase are built and green, an operator console ships
alongside, and the commercial productization program (3-tier packaging) is underway — waves 0–1 are
landed and the WS-D auth/metering edge is in. Suite: 787 tests passing, 10 skipped on a bare
checkout — and 797 passing / 0 skipped once the real external deps are live (the 10 skips are the
Postgres + OpenBao integration tests, validated against a GCP Cloud SQL instance and a Dockerized
OpenBao; see the Log).** Ten feature waves have landed on top of the core kernel since the Wave-2
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
(Okta/Auth0/Keycloak via OIDC discovery + JWKS rotation, layered on `JWTIdentityAdapter`) are now
**done** (see the top Log entry); the remaining WS-D/Wave-2 slice is **console OIDC login + per-tier
UI gating**.
**WS-C** (Stripe + Razorpay billing → tier flips; usage metering on the access log) is now **done**
(see the top Log entry). **WS-F** (regulator ledger-proof export) is now **done** too. Remaining:
**WS-E** (Enterprise isolation hardening) and **WS-G** (GDPR crypto-shredding erasure). The pre-sale
blockers below (K·02 crypto review, policy content packs) remain open in parallel.

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
  approvals), but auth is token-paste (no login/OIDC), there are no model-registry (K·08) / consent
  (K·04) / tenant-config surfaces yet, and HITL approval→action-resumption needs the async K·06
  deployment (the synchronous lifecycle times a gate out). Charts are minimal CSS.

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
