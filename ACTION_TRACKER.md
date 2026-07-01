# QUAICU Kernel — Deployment-Readiness Action Tracker

> **Reset 2026-06-28.** The prior wave breakdown (W0–W8) was cleared from this file and replaced by the
> Deployment-Readiness Program below. Historical wave detail + the dated Progress Log remain in git
> history and in `New/quaicu-kernel/docs/adr/BUILD_JOURNAL.md` (Log). This file is now the granular,
> task-level tracker for taking the kernel to **production deployment**.

**How to use:** work top-to-bottom within a phase; phases are **dependency-ordered**, not calendar-bound
(decision: *correctness over deadline*). Tick the box, set **Status**, append a dated note to the
Progress Log at the bottom. **Type** = `code` (we build) / `infra` (cloud/IaC/ops) / `human`
(legal/audit/process — calendar time, we only sequence + track).

**Status legend:** `TODO` · `IN-PROGRESS` · `BLOCKED` · `DONE` · `DEFERRED`.

---

## Program scope — decisions of record (2026-06-28)
- **Shapes:** ship **both** dedicated single-tenant **and** shared multi-tenant SaaS.
- **Cloud:** **GCP**. **Readiness bar:** all three — design-partner pilot + regulated-enterprise GA + cloud-marketplace listing.
- **Proof layer:** build the **trust anchor + external witness now**; the third-party crypto review is **deferred but scheduled/tracked** (T-1).
- **HITL channels:** **Microsoft Teams + Email** (reuse the existing Resend sender). Slack/Jira out of scope.
- **Integration surfaces:** **harden the Python SDK**, build the **MCP governance server**, extend the **gateway to tool-calls**. Non-Python SDKs out of scope.
- **Policy authoring:** **QUAICU-authored CEL packs** (services-led). Rule-builder UI / multi-step SOP authoring out of scope.
- **Ops model:** **mixed** — QUAICU operates the shared SaaS; dedicated instances are **customer-operated** (their GCP project, their KMS) with our IaC + runbooks + support.
- **HA/DR:** build the capability; commit specific SLA/RTO/RPO **per contract**.
- **Residency:** **per-customer configurable** GCP region (deploy-time parameter + residency matrix).
- **Identity:** keep generic OIDC; add **SAML 2.0** + **Entra/Azure AD** integration & certification.
- **Billing:** activate **live Razorpay** (India self-serve) + **invoice/contract** (enterprise). GCP Marketplace *metered* billing deferred → listing-readiness only.
- **Member auth:** build **in-browser member login** so a compliance member does maker/checker in the console.
- **Definition of done:** **all three** — a live pilot running end-to-end **and** an external security review passed **and** supply-chain + load + DR-restore green.

## Verified baseline corrections (don't trust the stale .md notes — confirmed in code 2026-06-28)
- `pyproject.toml` **exists** → packaging is partly done; the real gap is **no lockfile**.
- `EntitlementRepository` (`core/entitlements/repository.py`) + `PostgresEntitlementRepository`
  (`adapters/entitlements/postgres.py`) **exist** → durable entitlements are built; verify they are wired, not rebuild.
- `build_saas_app` (`delivery/sdk/saas_app.py:76`) + `TieredKernelProvider` (`delivery/sdk/provider.py:29`)
  **exist** → the shared-plane entrypoint exists; harden, don't write from scratch.
- Identity adapters present: `adapters/identity/{jwt_adapter,oidc}.py` only → **SAML is genuinely missing**.
- Billing adapters present: `adapters/billing/{razorpay,stripe,marketplace,razorpay_signup}.py` → need live keys + the absent `RAZORPAY_WEBHOOK_SECRET`, not new code.

---

## Phase D0 — Ground truth + supply-chain foundations (unblocks everything)

| ID | Task | Type | Status |
|----|------|------|--------|
| ☑ D0-1 | **State-of-durability audit.** Trace every component on the operated plane to confirm it runs on its Postgres adapter (action repo, entitlements, ledger, policy store, HITL store) and that RLS isolation (migration 004) is active end-to-end. **DoD:** a written, code-cited gap list; any remaining in-memory hot-path on the operated plane is identified with the file. → **`New/quaicu-kernel/docs/operations/DURABILITY_AUDIT.md`** | code | DONE |
| ☑ D0-2 | **Dependency lockfile.** Add a lockfile pinning the deps declared in `pyproject.toml` + `delivery/docker/Dockerfile`. **DoD:** reproducible `pip install` from the lock; image builds from the lock; lock checked in. Prereq for D0-3 SBOM. → base `requirements.lock` already existed (hash-pinned); **closed the floating `pip install google-cloud-kms`** with a hash-pinned `requirements-gcp.lock` (consistent superset of base + `gcp` extra) installed via `--require-hashes`. | code | DONE |
| ☑ D0-3 | **Supply-chain CI → blocking.** Extend `cloudbuild.yaml`: lint + unit tests (blocking) → build → **CycloneDX SBOM** artifact → **cosign** image signing → **Trivy + pip-audit as gates** (graduate from report-mode). **DoD:** a failing scan/lint/test fails the build; every pushed image is signed; SBOM emitted per build. → pip-audit + Trivy (HIGH,CRITICAL, `--ignore-unfixed`) now **blocking**; SBOM emitted every build; **cosign sign + SBOM-attest via Cloud KMS** (`--tlog-upload=false`, zero-egress-safe). **Operator one-time step:** provision the KMS `cosign-signer` key + grant the Cloud Build SA `signerVerifier`, set `_COSIGN_KMS_KEY` (see VULN_MANAGEMENT.md §3). | infra | DONE (config) · needs KMS provisioning |
| ☑ D0-4 | **Listing/legal artifacts.** Add `LICENSE`; confirm `README` + `SECURITY.md` are listing-grade. **DoD:** LICENSE present; README states what it is + how to deploy; SECURITY.md has a disclosure path. → root artifacts were already good; the **package** (`New/quaicu-kernel/`) had no LICENSE/README + no `pyproject` license metadata. Added package `LICENSE` + listing-grade `README.md`; wired `pyproject` (PEP 639 `license` + `license-files` + `readme` + classifiers + urls); confirmed `SECURITY.md` disclosure path + de-staled its supply-chain bullet. **Verified via `uv build`:** wheel METADATA carries `License-Expression` + bundled LICENSE + markdown README. Legal placeholders remain counsel's job (T-4). | code | DONE |
| ☑ D0-5 | **Durable hot-path closure → reframed: shared durable plane + upgrade = feature unlock** (owner decision). Replaced the two-kernel plane with **one durable kernel** (`kernel.shared.toml`) serving STARTER+BUSINESS on Postgres+KMS; tier is a pure feature gate (entitlements). No in-memory hot-path → `--workers > 1` safe (resolves D0-1 Gap 1); a STARTER→BUSINESS upgrade moves **no data**. Added explicit fail-closed `max_policies` gating (5b) + raised caps (STARTER 200 / BUSINESS 1000). ADR-0013. **DoD:** unit suite green (1041); integration proofs **green live** against GCP Cloud SQL (`tests/conformance/storage/test_shared_plane.py` — 3 passed). | code | DONE |

## Phase D1 — Make the human-approval loop actually work (demo-breaking)

*Files: `core/lifecycle/engine.py` (default `max_poll_attempts=1`, `defer_gate`, `resume_after_approval`),
`delivery/sdk/kernel.py` (`guard`/`wrap`/`generate`, `resume_approved`), `delivery/api/routes/approvals.py`,
`core/ports/hitl.py`, `core/hitl/model.py`, `core/hitl/store.py`, `adapters/hitl/` (+ new `email.py`, `teams.py`).*

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D1-1 | **Async-by-default approval on the SDK path.** Route `guard`/`wrap`/`generate` through the durable `defer_gate` + `resume_after_approval` flow that `/v1/actions/propose` already uses, so a `require_approval` action **suspends durably** instead of polling-once → `TIMED_OUT` → DENY. Keep fail-closed only on real infra failure. **DoD:** an SDK-decorated `require_approval` action returns PENDING and resumes+executes+seals on approval; no false DENY; test proves it. | code | TODO |
| ☐ D1-2 | **Email HITL adapter.** `EmailHITLAdapter` implementing `HITLPort`, reusing the existing Resend sender; sends an approval request with signed, expiring approve/reject links. **DoD:** approval round-trips via email link; link signature verified + single-use; config-selectable. | code | TODO · blocked-by D1-1 |
| ☐ D1-3 | **Microsoft Teams HITL adapter.** `MicrosoftTeamsHITLAdapter` (Adaptive Card with approve/reject actions + signed callback). **DoD:** card posts to a channel/webhook; approve/reject resolves the approval; tenant-isolated; config-selectable. | code | TODO · blocked-by D1-1 |
| ☐ D1-4 | **Durable, at-least-once delivery.** A delivery worker over the Postgres approval store (retry + dedupe); enrich `ApprovalRecord` with notification target/contact + a signed resume link. **DoD:** delivery survives a restart; no duplicate executions; record carries routing metadata. | code | TODO · blocked-by D1-1 |
| ☐ D1-5 | **In-browser member maker/checker.** Member login (password + IdP) so a `COMPLIANCE` member approves in the console, not only via API key; keep the self-approval guard. **DoD:** a member logs in and approves in-browser; self-approval blocked; sealed approver identity correct. | code | TODO |

## Phase D2 — Interception surfaces (cooperative → harder to bypass)

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D2-1 | **MCP governance server** (`delivery/mcp/`). A fail-closed MCP server that intercepts an agent's **tool calls**, maps each to an action (type + payload) → policy → HITL → seal, in one integration, no client-code change. **DoD:** an MCP client's tool calls are governed end-to-end (allow/deny/approval), each sealed; deny blocks the tool call; documented quickstart. | code | TODO |
| ☐ D2-2 | **Gateway tool-call governance.** Extend `delivery/api/routes/ai_gateway.py` + `delivery/api/ai_providers.py` beyond chat-completions to **tool/function calls** (and embeddings) across providers; govern the tool call as the action. **DoD:** a provider tool-call flows through policy + masking + seal; tests per provider shim. | code | TODO |
| ☐ D2-3 | **Python SDK hardening.** Error semantics, async-approval ergonomics (pairs with D1-1), worked examples + docs. **DoD:** documented, typed, examples run green; clear exceptions on deny/halt/timeout. | code | TODO · blocked-by D1-1 |

## Phase D3 — Proof layer: trust anchor + external witness (anchor now, audit later)

*Files: `core/regmap/export.py` (`verify_ledger_proof_bundle`), `core/ledger/signer.py`,
`core/ledger/engine.py`, `adapters/ledger/{gcp_kms,aws_kms,openbao}.py`; new `core/ledger/anchor.py` + witness adapter.*

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D3-1 | **Key attestation / pinning.** Stop trusting the public key embedded in the bundle. Establish an out-of-band key identity (published key registry / pinned per-tenant `key_id`); change `verify_ledger_proof_bundle` to verify against an **externally supplied/pinned** key, not the bundle's own. Document the trust model. **DoD:** a bundle signed by an unknown/forged key **fails** verification; a correct externally-pinned key passes; test covers both. | code | TODO |
| ☐ D3-2 | **External witness / anchoring.** Periodically publish each tenant's STH to an independent anchor (**decide in this task:** RFC-3161 TSA vs a witness service vs a public append-only endpoint) + continuous consistency-proof checking across successive STHs; surface anchor proofs in the export bundle. **DoD:** a split-view / silent-rewind attempt is detected by the witness/consistency monitor; anchor proof present + verifiable in the bundle. | code | TODO · blocked-by D3-1 |
| ☐ D3-3 | **Crypto-review readiness.** Freeze the ledger/anchor surface and prep the K·02 review package (the audit itself is tracked in T-1). **DoD:** the anchored proof design + verifier are documented and frozen for review. | code | TODO · blocked-by D3-2 |

## Phase D4 — Multi-tenancy, isolation, packaging for both shapes

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D4-1 | **Shared SaaS hardening (we operate).** Make `build_saas_app` behind `TieredKernelProvider` the production entrypoint: verify per-tenant RLS isolation, durable everything, `--workers > 1`, autoscaling, graceful shutdown. **DoD:** load test passes multi-worker; isolation test green; clean rolling deploy. | infra | TODO · blocked-by D0-5 |
| ☐ D4-2 | **Dedicated single-tenant (customer-operated).** Per-customer GCP-project Terraform (reuse `deploy/terraform/gcp-enterprise/`), **customer-held Cloud KMS** signing root + BYO-keys, install/upgrade/rotate runbooks, support model. **DoD:** a dedicated instance stands up from IaC in a clean project with a customer KMS key; runbooks validated by a dry-run. | infra | TODO · blocked-by D3-1 |
| ☐ D4-3 | **Residency parameterization.** Region as a deploy-time parameter (reuse `regions/{eu,india,gulf}.tfvars`); residency matrix doc; opt-in zero-egress (VPC-SC) perimeter. **DoD:** deploy to a non-US region from IaC; residency matrix published; zero-egress validated for one zone. | infra | TODO · blocked-by D4-1 |

## Phase D5 — Identity, billing, operability

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D5-1 | **SAML 2.0 adapter.** New SAML SSO adapter alongside `adapters/identity/oidc.py`. **DoD:** SAML login works against a test IdP; assertions mapped to actor/roles; tenant-isolated. | code | TODO |
| ☐ D5-2 | **Entra/Azure AD integration + certification.** OIDC/SAML against Entra; pursue certification (pairs with the Teams channel D1-3). **DoD:** Entra SSO verified; certification submission prepared. | code+human | TODO · blocked-by D5-1 |
| ☐ D5-3 | **Live Razorpay.** Complete KYC + provision the absent `RAZORPAY_WEBHOOK_SECRET`; enable `[billing.razorpay]`. Enterprise stays invoice/contract. **DoD:** a live ₹ payment + webhook tier-flip works on staging; webhook signature verified. | infra+human | TODO |
| ☐ D5-4 | **Observability + status (operated plane).** Log-based metrics + alerts + uptime check; `status.` page; on-call rotation. **DoD:** alerts fire on synthetic failure; status page live; rotation staffed. | infra | TODO · blocked-by D4-1 |
| ☐ D5-5 | **Resilience.** Run the **DR restore test**; stand up the retention-locked **WORM** bucket; trust-center page. **DoD:** a restore drill meets the (per-contract) RTO/RPO and is documented; WORM bucket live; trust center published. | infra | TODO · blocked-by D5-4 |

## Phase D6 — Acceptance (definition of done = ALL of these)

| ID | Task | Type | Status |
|----|------|------|--------|
| ☐ D6-1 | **Live pilot end-to-end.** One real tenant: an agent governed end-to-end → sealed → proof bundle **externally verified against the pinned anchor**. **DoD:** the full flow runs on both a dedicated instance and the shared plane. | infra | TODO · blocked-by D2-1, D3-2, D4-2 |
| ☐ D6-2 | **External security review passed.** Independent pen-test + security review clean (booking tracked in T-3). **DoD:** report received; criticals/highs remediated. | human | TODO |
| ☐ D6-3 | **Supply-chain + resilience green.** CI/SBOM/signed-images/vuln green **+** load test **+** DR restore test passed. **DoD:** all gates green in one release candidate. | infra | TODO · blocked-by D0-3, D4-1, D5-5 |

---

## Tracked non-code workstream (parallel; we sequence, others execute)

| ID | Item | Status |
|----|------|--------|
| ☐ T-1 | **Commission K·02 ledger crypto review** (the proof anchor depends on this for credibility). RFQ is send-ready (`docs/operations/CRYPTO_REVIEW_RFQ.md`). | TODO · gated-by D3-3 |
| ☐ T-2 | **SOC 2** (Type I → II observation window) — start the clock. | TODO |
| ☐ T-3 | **Independent pen-test** — book a firm (SoW drafted, `docs/compliance/PENTEST_SOW.md`). | TODO · feeds D6-2 |
| ☐ T-4 | **DPA/MSA counsel sign-off** (starters drafted under `docs/legal/`). | TODO |
| ☐ T-5 | **RBI/DPDP + credit-lending pack legal/CRO review** before activation in a real tenant; the console legal "draft" banner stays until counsel clears it. | TODO |

---

## Reuse (do not rebuild)
- **Email:** existing Resend sender (signup OTP) → D1-2. **Async approval:** `defer_gate` + `resume_after_approval` already in `core/lifecycle/engine.py` → D1-1. **Durable state:** `PostgresEntitlementRepository` + Postgres ledger/policy/HITL adapters → D0-5/D4-1. **IaC:** `deploy/terraform/gcp-{saas,enterprise}/` + region presets → D4-*. **Verifier scaffolding:** `core/regmap/export.py` → D3-*. **CI base:** `cloudbuild.yaml` → D0-3. **Billing:** `adapters/billing/*` → D5-3.

## Open items to resolve during execution
- D3-2 anchor mechanism choice (TSA vs witness service vs public endpoint).
- Confirm GCP Marketplace *metered* billing stays deferred (listing-readiness only).
- Explicitly out of scope this program: non-Python SDKs, rule-builder UI, multi-step SOP authoring, Slack/Jira HITL.

---

## Progress Log
_Append dated entries as items move. Format: `- [YYYY-MM-DD] (who) ID — what changed`_

- [2026-07-01] (claude) **D0-5 DONE (code) — shared durable plane + upgrade = feature unlock** (owner reframe of the original "durable hot-path closure"). **5a:** new `delivery/docker/kernel.shared.toml` (one durable kernel, Postgres+KMS, `default_profile=standard`); `TieredKernelProvider.for_shared_saas`; `build_saas_app` → single `[plane] config`; `kernel.saas.toml`/Dockerfile updated; `TIER_MATRIX` STARTER→durable adapters (BUSINESS superset). **5b:** collapsing kernels removed the structural feature-wall, so added explicit fail-closed `max_policies` enforcement at `register_policy` (+ tenant-stamp so the count is non-bypassable; `QuotaExceededError`→429); confirmed no profile selector exists and left the BYO AI gateway open to all tiers (owner decision). **5c:** raised caps STARTER 5→200 / BUSINESS 200→1000; wrote real-Postgres integration proofs (`tests/conformance/storage/test_shared_plane.py`: cross-worker idempotency + restart durability + upgrade-is-metadata-only); ADR-0013 + DURABILITY_AUDIT Gap 1 marked RESOLVED + deploy docs updated. Unit suite **1041 passed**, ruff clean. **Live-verified 2026-07-01:** ran `tests/conformance/storage/test_shared_plane.py -m integration` against the GCP Cloud SQL instance (`quaicu-pg`, via the Auth Proxy on :5433, `alembic upgrade head` applied) → **3 passed** (cross-worker idempotency, restart durability, upgrade-is-metadata-only). One test-only fix during the run: `ActionState.EXECUTED`→`COMPLETED`.
- [2026-07-01] (claude) **D0-4 DONE — package listing/legal artifacts.** The repo-root LICENSE/README/SECURITY were already listing-grade, but the **distributable package** (`New/quaicu-kernel/`) shipped with none of the licensing metadata: no `LICENSE`, no `README.md`, and `pyproject.toml` had no `license` field + a placeholder inline `readme`. Added `New/quaicu-kernel/LICENSE` (verbatim mirror of the proprietary license, placeholders left for counsel/T-4) + a concise, accurate, listing-grade `New/quaicu-kernel/README.md` (what it is, install, **how to deploy** via the kernel.*.toml profiles + Terraform/Cloud-Run doc links; uses the real `Kernel.from_config`/`@kernel.guard` API, not the root README's stale `from_parts(api_key=…)` snippet). Wired `pyproject.toml` PEP 639: `readme="README.md"`, `license="LicenseRef-Proprietary"`, `license-files=["LICENSE"]`, `[project.urls]`, classifiers (incl. `Private :: Do Not Upload`), bumped `setuptools>=77`. De-staled `SECURITY.md`'s supply-chain bullet to match D0-3 (blocking scans + cosign/SBOM). **Verified:** `uv build` produces sdist+wheel; wheel METADATA carries `License-Expression: LicenseRef-Proprietary`, bundled `LICENSE`, and the markdown README long-description. No source code changed.
- [2026-07-01] (claude) **D0-3 DONE (config) — supply-chain CI graduated to blocking.** Edited `New/quaicu-kernel/cloudbuild.yaml`: pip-audit now blocking and audits **both** locks (base + gcp superset); Trivy now `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` (blocking, matching the already-shipped `release.yml` gate); CycloneDX SBOM emitted every build (no `|| true`); push now captures the immutable digest; **new `cosign-sign` step signs the pushed digest + attaches a CycloneDX SBOM attestation using a Cloud KMS HSM key** (`gcpkms://`, `--tlog-upload=false` → sovereign, zero-egress/VPC-SC-safe; user chose KMS over keyless). Added `New/quaicu-kernel/.trivyignore` (documented-exception list, empty) and updated `docs/operations/VULN_MANAGEMENT.md` (modes → blocking; §3 marked complete; one-time KMS key + IAM setup documented). YAML validated; no report-mode remnants. **Not runnable locally** (Cloud Build is billable/remote) — operator must provision the KMS `cosign-signer` key + grant the Cloud Build SA `roles/cloudkms.signerVerifier`, set `_COSIGN_KMS_KEY`, then `gcloud builds submit`. Feeds D6-3 (supply-chain green).
- [2026-06-30] (claude) **D0-2 DONE — dependency lockfile reproducibility.** Found the base `requirements.lock` already existed (uv-compiled, hash-pinned) and the Dockerfile already installs it with `--require-hashes`. The one real gap: the BUSINESS-tier Cloud KMS dep was installed floating + un-hashed (`pip install google-cloud-kms`), breaking full reproducibility (its comment even said to fix this). Generated `New/quaicu-kernel/requirements-gcp.lock` via `uv pip compile pyproject.toml --extra gcp --generate-hashes --constraint requirements.lock` — a hash-pinned **consistent superset** of the base lock + the `gcp` extra (zero shared-dep drift, confirmed). Changed the Dockerfile builder to `pip install --require-hashes -r requirements-gcp.lock`. Base lock stays SDK-free by design (`aws`/`redis` extras not on the operated plane → left unlocked). Verified: lock resolves under `--require-hashes` on Python 3.12 (image interpreter) via uv dry-run; full `docker build` not run locally (Docker Desktop daemon down) but the build path is unchanged except the now-hashed gcp layer. Unblocks D0-3 (SBOM).
- [2026-06-30] (claude) **D0-1 DONE — state-of-durability audit.** Traced the operated plane (`build_saas_app` → STARTER + BUSINESS kernels from `kernel.{starter,business}.toml`). Result: **BUSINESS is durable on every correctness-critical store** (postgres action repo/policy/ledger + postgres HITL queue); **entitlements + accounts durable** and `PostgresEntitlementRepository` genuinely wired (`entitlements_config.py:56`). Gaps, all code-cited in `docs/operations/DURABILITY_AUDIT.md`: (1) STARTER fully in-memory on the hot path — `_InMemoryActionRepository` at `delivery/sdk/kernel.py:71`, per-process idempotency + approvals → primary D0-5 target; (2) event bus in-memory both tiers (documented non-critical); (3) usage meter per-process (best-effort); (4) RLS covers only actions+ledger tables — policy/approvals/entitlements lack RLS + don't set the tenant GUC (follow-up isolation task); (5) no consent adapter on the operated plane (T-5 legal-gated). No source code changed.
- [2026-06-28] (claude) **Tracker reset to the Deployment-Readiness Program.** Cleared the W0–W8 wave breakdown (retained in git history + BUILD_JOURNAL Log) and replaced it with phases D0–D6 + a tracked non-code workstream, per the decisions of record above. Grounded in a fresh code pass that corrected stale go-live notes (pyproject + durable entitlements + SaaS entrypoint already exist; lockfile + SAML + proof-anchor + push-HITL + MCP/gateway-tool-calls are the real gaps). No code actioned yet.
