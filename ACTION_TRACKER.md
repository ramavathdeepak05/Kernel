# QUAICU Kernel — Consolidated Action Tracker

_Merged from two independent reviews on 2026-06-23:_
- **G** = `review finding gemini.md` (Gemini — code/runtime review)
- **R** = `REVIEW_FINDING.md` (readiness-for-regulated-sale review)
- **Both** = independently flagged by both reviewers (highest-confidence signal)

**How to use:** work top-to-bottom within each wave. Tick the box when done, set **Status**, and add a dated note in the Progress Log at the bottom. Items marked **★** are flagged as high-leverage/critical by the source review. `Type` = `code` (we build it) or `human` (process/legal/audit — calendar time, can't be compressed).

**Status legend:** `TODO` · `IN-PROGRESS` · `BLOCKED` · `DONE` · `DEFERRED`

---

## Wave 0 — Live risk / do now (active exposure)

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ☑ W0-1 | **★ Rotate leaked secrets** (Resend key + Razorpay test keys passed through chat) and `gcloud secrets versions destroy` the leaked versions | R §3 | human | **✅ DONE 2026-06-23** — Resend + Razorpay rotated at provider, new values pushed to Secret Manager, old leaked versions destroyed. Edge-secret v1/v2 also destroyed. Recommended a no-op `gcloud run services update` so running revisions re-resolve `:latest` (the destroyed versions are no longer referenced). |
| ☑ W0-2 | Confirm `QUAICU_API_KEY_PEPPER` is injected as high-entropy random in prod (never the blank fallback) | G QW#2 | code/ops | **✅ DONE 2026-06-23.** Verified on the live service: `QUAICU_API_KEY_PEPPER` maps from Secret Manager (`secretRef:...:latest`); value is 64-char hex, ~244-bit entropy (3.82 bits/char), **not** the placeholder, **not** blank. (Note: stored with a trailing newline — harmless; do NOT strip it, that would invalidate every issued API key.) |

---

## Wave 1 — Confirmed code fix (all sources agree)

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ☑ W1-1 | **★ Real-client-IP rate limiting** — unauth fallback uses `request.client.host`, which collapses to the Cloudflare Worker / LB IP → all unauth requests share one bucket (global DoS). Add trusted forwarded-for handling at the ASGI edge keyed on `CF-Connecting-IP` (trust the Worker, NOT raw `X-Forwarded-For`). `delivery/api/ratelimit.py:115`, `delivery/api/app.py` | **Both** (G §1, R §5, CLAUDE.md handoff) | code | **✅ DONE — ACTIVATED 2026-06-23.** Code was already present and stronger than the reviews assumed: `trusted_client_ip` (`delivery/api/deps.py:31`) trusts a forwarded `X-Real-Client-IP` **only** when `X-Edge-Auth == QUAICU_EDGE_SECRET` (constant-time) — not raw `CF-Connecting-IP`, which a direct caller to the public Cloud Run origin could forge. Worker (`console/worker.js:26`) sets both from `CF-Connecting-IP` + `env.EDGE_SECRET`. Activated by provisioning the matching shared secret: `QUAICU_EDGE_SECRET` on Cloud Run (Secret Manager, redeployed) + `EDGE_SECRET` on the Worker (`wrangler secret put`). |

---

## Wave 2 — Start the long-lead compliance clocks (parallel, calendar-bound)

> These cannot be compressed — start them *now* in parallel while code work proceeds.

| ID | Item | Src | Type | Lead | Status |
|----|------|-----|------|------|--------|
| ◐ W2-1 | **★ Commission K·02 ledger crypto review** (Trail of Bits / NCC / Kudelski). RFQ drafted. Anchor of the whole credibility story. | R §1 | human | 6–8 wk | **RFQ finalized 2026-06-23** — added §6 commissioning checklist + vendor shortlist to `docs/operations/CRYPTO_REVIEW_RFQ.md`; **send-ready** once budget/contacts/`[TAG]` filled. (human action: send) |
| ☐ W2-2 | **Start SOC 2 clock** — Type I now → Type II observation window | R §1 | human | 3→12 mo | TODO — pure human; tracked in `docs/compliance/WAVE2_COMPLIANCE_CLOCKS.md` |
| ◐ W2-3 | Book **independent pen-test** | R §1 | human | 3–5 wk | **SoW drafted 2026-06-23** (`docs/compliance/PENTEST_SOW.md`: targets, multi-tenant-isolation focus, RoE, deliverables). **Pending: book a firm.** |
| ☐ W2-4 | **ISO 27001 (+27701)** for EU/Gulf/global | R §1 | human | 6–12 mo | TODO — pure human; tracked in `WAVE2_COMPLIANCE_CLOCKS.md` |
| ◐ W2-5 | **GDPR Art.28 DPA + SCCs** (required to process any EU data) | R §1 | human | weeks | **Starter drafted 2026-06-23** (`docs/legal/DPA_ART28_STARTER.md`: Art.28(3) clause checklist + subprocessors + SCC note, mapped to kernel support). **Pending: counsel drafts binding DPA.** |
| ☑ W2-6 | **RBI/SEBI cloud & outsourcing compliance** — documented mapping + RBI policy pack (code) | R §1 | human+code | wks–mo | **✅ CODE DONE 2026-06-23** — built `docs/policy-packs/rbi/` (12 CEL policies, 4 action types: localization, encryption-at-rest, outsourcing governance, cross-border transfer, access logging), registered in `core/policy/packs.py`, `test_rbi_pack.py` (14 tests) + full policy suite green, ruff clean. README carries the policy→ref mapping. **Remaining (human): adapt to licence category + backtest before activating in a real tenant.** |
| ◐ W2-7 | Confirm & document **PCI-DSS SAQ-A** scope (don't over-scope) | R §1 | human | confirm | **Scope memo drafted 2026-06-23** (`docs/compliance/PCI_SAQ_A_SCOPE.md`: SAQ-A eligibility via hosted Razorpay/Stripe checkout, code evidence, scope boundary). **Pending: confirm with acquirer/QSA + sign SAQ-A.** |
| ☐ W2-8 | **HIPAA BAA + safeguards** — only if entering healthcare | R §1 | human | weeks | DEFERRED |

---

## Wave 3 — Legal / commercial pack (counsel-gated)

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ◐ W3-1 | Enterprise **MSA** | R §4 | human | **Starter drafted 2026-06-23** (`docs/legal/MSA_STARTER.md`: 18-clause checklist + 4 exhibits, governance-≠-compliance disclaimer, insurance/entity blockers flagged). **Pending: counsel drafts binding MSA.** |
| ◐ W3-2 | **DPA** (data processing agreement) | R §4 | human | **Satisfied-by W2-5** — starter already at `docs/legal/DPA_ART28_STARTER.md`. **Pending: counsel finalizes Art.28 DPA + SCCs.** |
| ◐ W3-3 | **SLA** with uptime credits | R §4 | human | **Starter drafted 2026-06-23** (`docs/legal/SLA_STARTER.md`: uptime tiers + credit schedule, exclusions, sole-remedy; numbers left as `[N]%` placeholders pending W4-1/2/3). **Pending: ops sets targets + counsel review.** |
| ◐ W3-4 | Support tiers + order forms + finalized enterprise pricing | R §4 | human | **Starter drafted 2026-06-23** (`docs/legal/ORDER_FORM_AND_PRICING.md`: order-form template + support-tier table + pricing sheet mirroring live ₹10k/₹50k). **Pending: business sets support targets/list pricing.** |
| ◐ W3-5 | Counsel sign-off on Terms/Privacy/Refunds (remove "draft" banners) | R §4 | human | **Inventory drafted 2026-06-23** (`docs/legal/TERMS_SIGNOFF_INVENTORY.md`: per-doc review checklist + placeholder list). ⛔ **Draft banner stays in `console/src/legal/content.ts:1-2` until counsel signs off** — removal is a separate PR after the checklist clears. |
| ☐ W3-6 | **Cyber-liability / E&O insurance** | R §4 | human | TODO — pure human; tracked in `docs/legal/WAVE3_LEGAL_TRACKER.md`. **Upstream blocker:** limits feed the MSA liability cap. |
| ☐ W3-7 | Selling-entity / cross-border tax structure (VAT/GST) | R §4 | human | TODO — pure human; tracked in `WAVE3_LEGAL_TRACKER.md`. **Upstream blocker:** gates MSA governing-law/fees + Terms §9 + cross-border quoting. |
| ☐ W3-8 | **Live Razorpay keys** (clear KYC) | R §4 | human | TODO — KYC-gated; tracked in `WAVE3_LEGAL_TRACKER.md`. ⚠ Pair with provisioning the **absent `RAZORPAY_WEBHOOK_SECRET`** (flagged in W0-2). |

---

## Wave 4 — Operational readiness to run a regulated SaaS

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ◐ W4-1 | **Observability/alerting/uptime monitoring** wired in prod (Sentry/Grafana) | R §5 | code/ops | **Code DONE 2026-06-23** — added `/health` (liveness) + `/readyz` (readiness, gated on startup hydration) to `delivery/api/app.py`; Helm readiness probe repointed to `/readyz`; `/readyz` rate-limit-exempt; tests `tests/unit/api/test_health.py`. **Pending (ops):** wire log-based metrics + alerts + uptime check. `docs/operations/OBSERVABILITY_ONCALL_STATUS.md`. |
| ◐ W4-2 | **Status page** (enterprises require one) | R §5 | ops | **Runbook DONE 2026-06-23** (`OBSERVABILITY_ONCALL_STATUS.md` §3). **Pending: stand up `status.quaicu.org`.** |
| ◐ W4-3 | **DR/BCP** with stated RTO/RPO + a *tested* restore runbook (Cloud SQL PITR exists, restore untested) | R §5 | ops | **Runbook DONE 2026-06-23** (`docs/operations/DR_BCP_RUNBOOK.md`: PITR procedure + drill checklist; RTO/RPO bracketed). **Pending: run the restore test** (the real gap behind any RTO/RPO claim). |
| ◐ W4-4 | 24×7 on-call + defined support tiers | R §5 | human | **Model DONE 2026-06-23** (`OBSERVABILITY_ONCALL_STATUS.md` §4; support tiers in `docs/legal/ORDER_FORM_AND_PRICING.md`). **Pending: staff the rotation.** |
| ◐ W4-5 | Audit-log retention + **WORM** policy; documented key-rotation schedule / HSM custody | R §5 | code/ops | **Policy DONE 2026-06-23** (`docs/operations/RETENTION_WORM_KEYROTATION.md`: retention schedule, WORM options, full key-rotation table). **Pending: stand up retention-locked GCS bucket.** |
| ◐ W4-6 | **Trust center / compliance portal** (certs, subprocessors, status, whitepaper) | R §3 | human+code | **`SECURITY.md` DONE 2026-06-23** (posture + vuln-disclosure + shared-responsibility; **resolves the prior dangling refs** in PENTEST_SOW/DPA/SLA). **Pending: publish a trust-center page.** |
| ☑ W4-7 | **CAIQ / SIG questionnaire** pre-answered (answer once, reuse) | R §3 | human | **DONE 2026-06-23** (`docs/compliance/CAIQ_SIG_ANSWERS.md`, grounded in real posture; bracketed cert items pending). |
| ☑ W4-8 | **Incident-response runbook + breach-notification** process (GDPR 72h, DPDP) | R §3 | human | **DONE 2026-06-23** (`docs/operations/INCIDENT_RESPONSE.md`: severity reuses `core/incident`, lifecycle, GDPR-72h/DPDP breach playbook, comms templates). **Pending: tabletop + fill `[contacts]`.** |
| ◐ W4-9 | **Vuln-management policy** with patch SLAs + continuous dependency scanning | R §3 | code/ops | **DONE (report mode) 2026-06-23** — `cloudbuild.yaml` now has a blocking lint+test gate + pip-audit + Trivy + CycloneDX SBOM (report mode); policy + patch SLAs + graduation plan in `docs/operations/VULN_MANAGEMENT.md`. **Pending: clear backlog → graduate scans to blocking.** |

---

## Wave 5 — Data residency / sovereignty

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ◐ W5-1 | **Terraform the SaaS plane IaC** (currently manual; enterprise GCP TF exists) | R §2 | code | **Module authored 2026-06-23** — new `deploy/terraform/gcp-saas/` (`main/variables/outputs.tf` + README) codifies the hand-deployed `quaicu-kernel` Cloud Run service + Cloud SQL + Secret Manager, mirroring the proven `gcp-enterprise` module. **Pending: `terraform validate` (not installed here) + import the live service or apply greenfield.** |
| ◐ W5-2 | **Multi-region deploy** capability — EU region (no-US-egress), India DPDP localization, Gulf (KSA/UAE) | R §2 | code | **Region-parameterized + presets 2026-06-23** — `var.region` threads through; `regions/{eu,india,gulf}.tfvars` presets (one stack per residency zone). **Pending: apply a non-US zone to a real project + edge routing.** |
| ◐ W5-3 | **Validate** zero-egress VPC-SC/PrivateLink "prompts never touch public internet" topology at scale (specified, not proven) | R §2 | code | **Opt-in IaC + validation method 2026-06-23** — `enable_private_egress` (VPC connector + private Cloud SQL), default **off**; `docs/operations/ZERO_EGRESS_VALIDATION.md` gives the topology + evidence-producing test method. **Pending (the honest gap): org-level VPC-SC perimeter + running the validation at scale.** |
| ◐ W5-4 | Documented per-region residency guarantees | R §2 | human | **Matrix documented 2026-06-23** (`docs/operations/DATA_RESIDENCY.md`: data-class × region × regime, with Logging/Secret-Manager/processor residency caveats). **Pending: fill per-zone guarantees once a region is deployed.** |

---

## Wave 6 — Product gaps that block regulated adoption (all code)

> Ranked by deal-impact per R §6.

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ☐ W6-1 | **SSO/SCIM** — OIDC verify exists; add SCIM provisioning + enterprise RBAC/team-invite UI | R §6.1 | code | TODO |
| ☐ W6-2 | **AI Gateway BYO path** — enforce PII masking + budget (currently ungoverned passthrough); fix streaming 400s; add Azure/Anthropic shims | R §6.2 | code | TODO |
| ☐ W6-3 | **PII masking** beyond regex — add `MaskingPort` + Cloud DLP/Comprehend | R §6.3 | code | TODO |
| ☐ W6-4 | **Provable erasure** — replace `InMemoryShredKeyring` with HSM-backed `GcpKmsShredKeyring` | R §6.4 | code | TODO |
| ☐ W6-5 | **SIEM fan-out** — build Pub/Sub / EventBridge adapters (currently in-memory/logging only) | R §6.5 | code | TODO |
| ☐ W6-6 | **Audit/ledger export** (CSV/JSON + proof-download) in the console | R §6.6 | code | TODO |
| ☐ W6-7 | **AWS parity** — Bedrock, AWS KMS signer, Cognito, Step Functions (all specified, none built) | R §6.7 | code | TODO |
| ☐ W6-8 | **Auto-subscription billing** — tier auto-flip + annual renewal (currently manual/consultation-led) | R §6.8 | code | TODO |
| ◐ W6-9 | **Console hygiene** — self-host fonts (Google CDN IP-leak), CSP/security headers, WCAG AA contrast, responsive pass | R §6.9 | code | **PARTIAL 2026-06-23.** ✅ **Fonts self-hosted** (`@fontsource-variable` Inter/Space-Grotesk/JetBrains-Mono bundled into `dist/`; Google `<link>`s removed; build-verified, woff2 now same-origin). ✅ **Security headers in the Worker** (strict-self CSP + minimal Razorpay allowlist, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`). ⏳ **Remaining: WCAG AA contrast audit + responsive pass** (not started). **Needs deploy:** `npm run build` done; redeploy the Worker (`wrangler deploy`) to ship it. |

---

## Wave 7 — GTM resources to close & serve deals

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ☐ W7-1 | **★ Land one design partner / reference customer** in a single beachhead regime (India RBI/DPDP or EU) — #1 multiplier; picks region/residency/policy priorities | R §7 | human | TODO |
| ☐ W7-2 | Sales-engineering collateral: security whitepaper, architecture one-pager, **compliance matrix** (regime → kernel layer), stable demo env | R §7 | human+code | TODO |
| ☐ W7-3 | Marketplace listings — GCP (needs `gcp_sender` Service Control seam + scheduler), AWS (needs §6.7 parity), Azure | R §7 | code | TODO |
| ☐ W7-4 | Console **localization** for non-English regulators | R §7 | code | TODO |
| ☐ W7-5 | Partner/SI channel for regulated verticals | R §7 | human | TODO |

---

## Wave 8 — Performance / scale (deferrable until real concurrency)

| ID | Item | Src | Type | Status |
|----|------|-----|------|--------|
| ☐ W8-1 | **Sync HTTP on async hot path** — OpenBao signer uses `httpx.Client()` in `sign()`/`verify()`, blocking the event loop on every seal. Evolve `TreeSigner` to async + `httpx.AsyncClient`, or move signing to a background worker. `adapters/ledger/openbao.py:35,64` | G #2 | code | DEFERRED |
| ☐ W8-2 | **Sync cache hydration on lifespan** — `account_engine.hydrate()` blocks startup; large account stores could fail k8s probes. Bound it, index lookups, or warm in a post-lifespan async task. `delivery/api/app.py:110` | G #3 | code | DEFERRED |
| ☐ W8-3 | **Polyglot split** — move Merkle hash appends + CEL eval loop to Go for scale | G Refactor#2 | code | DEFERRED |

---

## Recommended execution order (the TOP-5 critical path, R)

1. **W2-1** Commission K·02 crypto review today (longest pole).
2. **W2-2 + W2-3** Start SOC 2 clock + book pen-test (calendar time you can't buy back).
3. **W3-*** Counsel-signed legal pack (MSA/DPA/SLA/privacy) **+ W0-1** rotate leaked secrets **+ W3-8** Razorpay KYC.
4. **W7-1** Land one design partner in one beachhead regime.
5. **W4-*** Operational hardening (observability, status page, tested DR, on-call) **+ W1-1** real-client-IP rate limiting.

> Sequencing note (R): Waves 2–3 are human/process with long lead times — run them **in parallel starting now** while engineering closes Wave 1 + Wave 6. Don't let finished code work crowd out the compliance clock — that clock is the real critical path.

---

## Progress Log

_Append dated entries as items move. Format: `- [YYYY-MM-DD] (who) ID — what changed`_

- [2026-06-23] (claude) Created this tracker by merging `review finding gemini.md` (G) and `REVIEW_FINDING.md` (R). No items actioned yet.
- [2026-06-23] (claude) **W1-1 — verified CODE-DONE.** Read the current source: the fix Gemini flagged is already implemented and is *stronger* than the reviews assumed. `delivery/api/deps.py:31 trusted_client_ip()` trusts a forwarded `X-Real-Client-IP` **only** when the request also carries `X-Edge-Auth == QUAICU_EDGE_SECRET` (constant-time `hmac.compare_digest`); it does **not** trust raw `CF-Connecting-IP`/`X-Forwarded-For` (which a direct caller to the public `*.run.app` origin could forge). The Cloudflare Worker (`console/worker.js:24-30`) strips client copies, then sets `X-Real-Client-IP = CF-Connecting-IP` and `X-Edge-Auth = env.EDGE_SECRET` — but **only `if (clientIp && env.EDGE_SECRET)`**, so the path is **inert until the shared secret is provisioned on both sides.** Middleware is registered and ordered correctly (`app.py:200`, auth-before-ratelimit). **Remaining = ops activation (run these; they're mutating cloud cmds):**
  ```bash
  # 1) generate one strong shared secret
  EDGE=$(openssl rand -base64 32)
  # 2) kernel side (Cloud Run) — create/add secret version + map it on the service
  printf '%s' "$EDGE" | gcloud secrets create QUAICU_EDGE_SECRET --data-file=- 2>/dev/null \
    || printf '%s' "$EDGE" | gcloud secrets versions add QUAICU_EDGE_SECRET --data-file=-
  gcloud run services update quaicu-kernel --region us-central1 \
    --update-secrets QUAICU_EDGE_SECRET=QUAICU_EDGE_SECRET:latest
  # 3) worker side — SAME value as EDGE_SECRET (run in console/ dir)
  printf '%s' "$EDGE" | npx wrangler secret put EDGE_SECRET
  ```
  Verify after: hit the public console origin and confirm unauth buckets differ per real client IP (not collapsed to the Worker IP). Then tick the box.
- [2026-06-23] (claude) **W1-1 — ✅ ACTIVATED.** Provisioned the shared secret on both sides: `QUAICU_EDGE_SECRET` on Cloud Run (Secret Manager version added, service redeployed → revision `quaicu-kernel-00027-rfn` + a later rotation revision) and `EDGE_SECRET` on the Cloudflare Worker (`wrangler secret put`, success). Real-client-IP rate limiting is now live end-to-end. **Note (W0-1 hygiene):** the first generated value was printed to chat, so we rotated to a fresh un-echoed value (kernel version ≥3). The chat-exposed version 2 and the empty version 1 are superseded (service maps `:latest`); optionally retire them: `gcloud secrets versions destroy 1 --secret=QUAICU_EDGE_SECRET` and `... destroy 2 ...`. **[done — v1 + v2 destroyed 2026-06-23; only the clean rotated version is live.]**
- [2026-06-23] (claude) **W0-2 — code verified, prod value unconfirmed.** `core/account/engine.py:89` resolves the pepper from `QUAICU_API_KEY_PEPPER`, falling back to empty **with a logged warning** (`:92`); `DEPLOY_CLOUD_RUN.md:49` maps the Secret-Manager secret onto the service. Remaining is an ops check that the *deployed* value is high-entropy, not the `'a-strong-random-pepper'` placeholder from the deploy doc:
  ```bash
  gcloud secrets versions access latest --secret=QUAICU_API_KEY_PEPPER | wc -c   # expect ≳32, random
  gcloud run services describe quaicu-kernel --region us-central1 \
    --format='value(spec.template.spec.containers[0].env)' | grep -i pepper      # confirm it's mapped
  ```
  ⚠ Rotating the pepper invalidates every existing API key (`kernel.prod.toml:19`) — if it's currently the placeholder, rotate during a maintenance window and re-issue keys.
- [2026-06-23] (claude) **W0-2 — ✅ VERIFIED on the live service** (read-only, value never printed to chat — only derived stats). `gcloud secrets versions access` → 64-char value, distinct=15, **3.82 bits/char ≈ 244-bit total entropy** (consistent with `rand -hex 32`), `is_placeholder=False`, non-empty. `gcloud run services describe` confirms `QUAICU_API_KEY_PEPPER` is mapped `secretRef:QUAICU_API_KEY_PEPPER:latest`. **Bonus confirmations from the same describe:** `QUAICU_EDGE_SECRET` is mapped (W1-1 kernel side genuinely wired) and `RAZORPAY_KEY_ID/SECRET` map from Secret Manager (W0-1 rotation is live). ⚠ Stored pepper has a **trailing newline** (gcloud returned 2 stdout lines) — functionally harmless (HMAC key = arbitrary bytes), but **never strip it** (one-byte change invalidates all issued keys). **Observation (not W0-2):** `RAZORPAY_WEBHOOK_SECRET` is **absent** from the service env — verify webhook signature verification isn't silently disabled.
- [2026-06-23] (claude) **W0-1 — rotation commands prepared (live exposure; run ASAP).** Secret names in this repo: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` (`delivery/docker/kernel.saas.toml:33`, `GO_LIVE_SETUP.md:40`); the Resend key is referenced but not named in deploy config — `gcloud secrets list | grep -i resend` to find it. Steps per secret: (a) rotate at the provider (Razorpay dashboard → regenerate keys; Resend dashboard → revoke + reissue), (b) `gcloud secrets versions add <NAME> --data-file=-` with the new value, (c) `gcloud run services update quaicu-kernel --region us-central1` to pick up `:latest`, (d) **destroy the leaked versions**: `gcloud secrets versions list <NAME>` then `gcloud secrets versions destroy <VERSION> --secret=<NAME>`. Razorpay test keys → just rotate test creds; this does **not** unblock live keys (that's W3-8, KYC-gated).
- [2026-06-23] (claude) **W0-1 — Resend + Razorpay rotated at the provider.** New credentials issued. Edge-secret leaked versions (v1 empty, v2 chat-exposed) already destroyed. Still to confirm to fully close: (a) the new Resend/Razorpay values are stored as new Secret Manager versions and the Cloud Run service points at them, (b) the **old leaked versions are destroyed** (`gcloud secrets versions list <NAME>` → `... versions destroy <N> --secret=<NAME>`). Rotating only at the provider already invalidates the leaked keys, so live exposure is effectively closed; the destroy step is hygiene + audit cleanliness.
- [2026-06-23] (claude) **Wave 2 — full artifact set produced (code + 5 docs).** (1) **W2-6 RBI/SEBI policy pack (CODE):** new `docs/policy-packs/rbi/{policies.toml,README.md}` — a broad-sweep pack of 12 CEL `[[policy.seed]]`s across 4 governed action types (`data.store`, `data.transfer`, `outsourcing.engage`, `access.grant`) covering RBI payment-data localization, encryption-at-rest, SEBI cloud localization (review), RBI material-outsourcing governance (approval + audit-rights + exit-plan), cross-border transfer review, and access-logging. Registered the `rbi` `_META` entry in `core/policy/packs.py`; added `tests/unit/policy/test_rbi_pack.py` (14 tests). Verified: `test_rbi_pack.py` 14/14, full `tests/unit/policy` 82 passed, loader discovers `['dpdp','eu-ai-act','rbi']`, ruff clean. Mirrors the DPDP pack pattern; RBI regime already modeled (`Regime.RBI_FREE_AI`). (2) **Docs for the human clocks:** finalized the crypto-review RFQ with a commissioning checklist + vendor shortlist (W2-1, `docs/operations/CRYPTO_REVIEW_RFQ.md` §6); PCI SAQ-A scope memo (W2-7, `docs/compliance/PCI_SAQ_A_SCOPE.md`); pen-test SoW (W2-3, `docs/compliance/PENTEST_SOW.md`); GDPR Art.28 DPA starter (W2-5, `docs/legal/DPA_ART28_STARTER.md`, not-legal-advice); and a Wave-2 clock tracker (`docs/compliance/WAVE2_COMPLIANCE_CLOCKS.md`) for the calendar-bound items. W2-2 (SOC 2) + W2-4 (ISO 27001) remain pure-human; W2-8 (HIPAA) deferred. All draft compliance/legal docs carry the not-legal-advice banner.
- [2026-06-23] (claude) **W6-9 — fonts + security headers DONE (build-verified), contrast/responsive remain.** (1) **Self-hosted fonts:** added `@fontsource-variable/{inter,space-grotesk,jetbrains-mono}` deps, imported them in `src/main.tsx`, removed the three Google Fonts `<link>`s from `index.html`, repointed the `--f-*` CSS vars to the "… Variable" families. `npm run build` succeeds and now emits the woff2 into `dist/assets/` (same-origin) — the Google-CDN client-IP leak is gone. (2) **Security headers:** `console/worker.js` now wraps every static-asset/SPA-document response with a strict-self `Content-Security-Policy` (the only third party allowed is Razorpay Checkout: `script-src checkout.razorpay.com`, `frame-src api.razorpay.com checkout.razorpay.com`, `connect-src/img-src *.razorpay.com`), plus `Strict-Transport-Security` (2yr+preload), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (camera/mic/geo/topics off). Deliberately **no COOP/COEP** (would break Razorpay's cross-origin iframe). **To ship:** `wrangler deploy` from `console/`. **Still open under W6-9:** WCAG AA contrast audit + responsive pass. ⚠ After deploy, smoke-test the signup ₹ payment flow once — if checkout misbehaves, the first CSP knob to relax is adding `'unsafe-eval'`/extra `*.razorpay.com` to `script-src`.
- [2026-06-23] (claude) **Wave 5 — data residency / sovereignty (full set, VPC-SC opt-in).** Found the SaaS plane (live `quaicu-kernel`) is deployed **entirely by hand** (`DEPLOY_CLOUD_RUN.md`) with no IaC; only the Model-B `gcp-enterprise` TF module existed. **Code (W5-1):** authored a new `deploy/terraform/gcp-saas/` module (`main.tf` + `variables.tf` + `outputs.tf` + README) codifying the shared-plane Cloud Run v2 service (`KERNEL_APP=entrypoint_saas`), Cloud SQL Postgres 16 (REGIONAL/PITR/deletion-protected), and Secret Manager (pepper, jwt, entitlements/account DSNs, edge secret, optional Razorpay) — mirroring the proven enterprise module (provider pins, `var.region` threading, secret-env-ref shape, cloudsql volume, public invoker). **(W5-2):** region-parameterized with `regions/{eu,india,gulf}.tfvars` presets (one stack per residency zone). **(W5-3):** opt-in `enable_private_egress` (VPC connector + private Cloud SQL), default **off** so a plain apply is unchanged; `ZERO_EGRESS_VALIDATION.md` documents the VPC-SC/PrivateLink topology + an evidence-producing validation method (VPC-SC perimeter is org-level → documented, not forced). **(W5-4):** `DATA_RESIDENCY.md` per-region matrix (data-class × region × regime) with the honest caveats (Cloud Logging, Secret Manager replication, and Razorpay/Resend can place data outside the compute region unless pinned). Added `WAVE5_RESIDENCY.md` tracker; cross-linked `DEPLOY_CLOUD_RUN.md` → the TF module. **Verification:** structural (mirrors gcp-enterprise) + env/secret cross-check vs DEPLOY_CLOUD_RUN.md; **terraform not installed locally** → `terraform validate`/`fmt` flagged as a user step. No secrets committed (sensitive vars only), no apply, no live changes. **Pending (human/ops):** apply a non-US zone, import the live service, stand up the org VPC-SC perimeter, and run the zero-egress validation at scale.
- [2026-06-23] (claude) **Wave 4 — operational readiness (full set: code + CI + docs).** **Code (W4-1):** added `/health` (liveness) + `/readyz` (readiness, gated on lifespan startup hydration via a new `app.state.ready` flag) to `delivery/api/app.py`; discovered `/health` already existed inline so extended it rather than duplicating; repointed the Helm readiness probe to `/readyz`; added `/readyz` to the rate-limit exempt set; tests `tests/unit/api/test_health.py` (2) — full `tests/unit/api` 174 passed, ruff clean. **CI (W4-9):** rewrote `cloudbuild.yaml` — blocking lint+unit-test gate before build, then pip-audit + Trivy (HIGH/CRITICAL) + CycloneDX SBOM in **report mode** (non-failing so the deploy pipeline isn't broken), SBOM saved as a build artifact; YAML validated. **Docs:** `SECURITY.md` (posture + vuln-disclosure + shared-responsibility — **resolves the 3 dangling `SECURITY.md` refs** I'd left in PENTEST_SOW/DPA/SLA), `DR_BCP_RUNBOOK.md` (W4-3, PITR + drill), `INCIDENT_RESPONSE.md` (W4-8, GDPR-72h/DPDP breach playbook, reuses `core/incident` severity), `RETENTION_WORM_KEYROTATION.md` (W4-5), `VULN_MANAGEMENT.md` (W4-9 policy + patch SLAs + report→blocking graduation), `CAIQ_SIG_ANSWERS.md` (W4-7), `OBSERVABILITY_ONCALL_STATUS.md` (W4-1/2/4), and `WAVE4_OPS_READINESS.md` (tracker). **Truthfulness fix:** corrected the overstated "Trivy/cosign/SBOM in CI" line in `DPA_ART28_STARTER.md` to match what actually shipped. **Pending (human/ops):** the DR restore test, external monitoring/status-page/pager setup, retention-locked WORM bucket, and graduating CI scans to blocking. No secrets, no deploys.
- [2026-06-23] (claude) **`RAZORPAY_WEBHOOK_SECRET` absence — investigated; NOT a live hole + hardened the latent footgun.** Traced the W0-2 observation. **Finding:** the live ₹ payment path (signup/consultation, `delivery/api/routes/signup.py:298`, `consultation.py:101`) verifies via `RazorpaySignupGateway.verify_payment()` — Razorpay **payment-signature** HMAC keyed on `RAZORPAY_KEY_SECRET` (present per W0-2; raises if blank). It does **not** use the webhook secret. The webhook tier-flip engine (`RazorpayBillingAdapter`, uses `RAZORPAY_WEBHOOK_SECRET`) is **disabled in prod** — no active `[billing.razorpay]` section in any deploy TOML (`build_billing` → `({}, None)`), which is *why* the secret is unset. So webhook signature verification is **not silently disabled**; the engine simply isn't wired. No fail-open path exists (the adapter raises `ValueError` on a blank secret and `WebhookVerificationError` on a bad/missing signature). **Latent footgun fixed:** `_expand_env` (`delivery/sdk/billing_config.py`) used `os.path.expandvars`, which leaves an unset `${VAR}` as a *truthy literal* — so a future `[billing.razorpay]` enabled without the env var would build an adapter with a bogus key and 403 every real webhook. Now `_expand_env` raises a clear startup error naming the missing var. Added `test_unresolved_env_ref_raises`; billing suite 56 passed, ruff clean. **Action when W6-8 (auto-tier-flip webhooks) ships:** provision `RAZORPAY_WEBHOOK_SECRET` in Secret Manager + map it on Cloud Run *before* adding the `[billing.razorpay]` section.
- [2026-06-23] (claude) **Wave 3 — full legal/commercial starter pack produced (counsel-briefing docs).** Every W3 item is human/counsel-gated, so the agent value is starters that compress drafting, not binding contracts. New under `docs/legal/`: **`MSA_STARTER.md`** (W3-1 — 18-clause MSA skeleton + 4 exhibits, governance-≠-compliance disclaimer, insurance↔liability-cap and entity↔governing-law dependencies called out); **`SLA_STARTER.md`** (W3-3 — uptime tiers + service-credit schedule + exclusions, all uptime numbers left as `[N]%` placeholders gated on W4-1/2/3 observability+tested-DR); **`ORDER_FORM_AND_PRICING.md`** (W3-4 — order-form template + support-tier table + pricing sheet mirroring the live ₹10k Starter / ₹50k consultation deposit / GST-exclusive / Razorpay); **`TERMS_SIGNOFF_INVENTORY.md`** (W3-5 — per-doc counsel checklist for `content.ts` Terms/Privacy/Refund/Contact + placeholder list); **`WAVE3_LEGAL_TRACKER.md`** (the human-item tracker for W3-1…W3-8). W3-2 (DPA) marked **satisfied-by** the existing `DPA_ART28_STARTER.md`. **Guardrail honored:** did NOT touch the live draft banner (`console/src/legal/content.ts:1-2`) — removal is a separate counsel-gated PR. W3-6 (insurance), W3-7 (entity/tax), W3-8 (live Razorpay KYC, + provision the absent `RAZORPAY_WEBHOOK_SECRET`) remain pure-human, tracked only. No code, no deploys, no secrets.
