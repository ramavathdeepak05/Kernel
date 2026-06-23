# QUAICU Kernel — Readiness Review for Regulated Global Sale

_Review date: 2026-06-23 · Scope: `New/quaicu-kernel` (knowledge-graph scan + strategy docs, build journal, backlog)_

## Verdict

**The engineering is essentially done. What's left is almost entirely *non-code*: the trust infrastructure regulated buyers actually gate on.** You have 14 governance layers, a tamper-evident ledger, multi-tenant RLS, a live SaaS plane, and ~940 green tests. That gets you a demo and a free tier. It does **not** get you a Tier-1 bank signature. Banks/insurers/hospitals don't buy on features — they buy on **attestations, contracts, and someone else's reference**. That's the gap.

Second framing point: **"sell globally" is the trap.** Each regime (RBI/DPDP, EU AI Act/GDPR, US SOC2/HIPAA, Gulf) has a different gate. Trying to clear all of them at once will stall you. Pick **one beachhead regime** for the first sale and sequence the rest. Given Razorpay is already live + DPDP/EU packs shipped, **India (RBI/DPDP) or EU is the natural first beachhead.**

---

## 1. Compliance attestations & certifications — *the real blockers*

| Item | Why a regulated buyer blocks | Lead time | Type |
|---|---|---|---|
| **K·02 ledger crypto review** (Trail of Bits / NCC / Kudelski) | Your whole pitch is "tamper-evident sovereign ledger." Unaudited crypto = no bank. RFQ is drafted. | **6–8 wk — longest pole; commission NOW** | Human |
| **SOC 2 Type II** | The universal US/global enterprise gate. Type I (~2–3 mo) unblocks pilots; Type II needs a 6–12 mo observation window. | 3 mo → 12 mo | Human + light code |
| **Independent pen-test** | Table-stakes; every security questionnaire asks for the report date. | 3–5 wk | Human |
| **ISO 27001 (+27701)** | Required for EU/Gulf/global enterprise; 27701 covers privacy. | 6–12 mo | Human |
| **GDPR Art.28 DPA + SCCs** | Legally required to process *any* EU customer data. | Weeks (counsel) | Human |
| **HIPAA BAA + safeguards** | Only if healthcare; gates that vertical entirely. | Weeks | Human |
| **RBI/SEBI cloud & outsourcing compliance** | For Indian banks: localization, auditability, exit/audit clauses. You're well-positioned (DPDP pack, ledger) but need the documented mapping. | Weeks–months | Human + **RBI pack (code, not written)** |
| **PCI-DSS** | Likely **SAQ-A only** (Razorpay/Stripe hosted checkout offloads cardholder data). Confirm and document — don't over-scope. | Confirm | Human |

**Critical insight:** SOC 2 Type II + ISO 27001 each take 6–12 months of *clock time you can't compress.* If a global regulated sale is the goal, **the certification clock should already be running.** Start the Type I + observation window immediately, in parallel with everything else.

---

## 2. Data residency / sovereignty / localization

- **Strength:** Your **Model B (customer-hosted single-tenant)** story sidesteps ~90% of residency objections — their project, their KMS, their data. This is your strongest regulated card. **But the Terraform for it exists only for enterprise GCP; the SaaS plane IaC is manual.**
- **Gaps:** SaaS plane is **single-region GCP**. EU residency needs an EU-region deployment with documented no-US-egress; India DPDP localization and Gulf (KSA/UAE) residency need the same. The zero-egress VPC-SC/PrivateLink topology is **specified but not proven at scale**.
- **Need:** Documented per-region residency guarantees + multi-region deploy capability + the "prompts never touch public internet" topology *validated*, not just diagrammed.

---

## 3. Security program artifacts (beyond the crypto review)

- **Have (good):** Trivy scan + cosign keyless signing + SBOM in CI; SECURITY.md drafted; HMAC-peppered API keys; fail-closed webhooks; RLS tenant isolation.
- **Missing & blocking:**
  - **Trust center / compliance portal** (public page: certs, subprocessors, status, security whitepaper). Buyers look here *first*.
  - **CAIQ / SIG questionnaire** pre-answered. You'll get one per deal — answer it once, reuse.
  - **Incident-response runbook + breach-notification process** (GDPR 72h, DPDP). Not present.
  - **Vuln-management policy** with patch SLAs; continuous dependency scanning.
  - **★ Rotate the exposed secrets** (Resend key + Razorpay test keys passed through chat) and `gcloud secrets versions destroy` the leaked versions. This is a live finding, not a future task.

---

## 4. Contractual / commercial

- **Have:** Terms/Privacy/Refunds drafted (still carry a "draft — counsel review" banner), pricing draft, Razorpay signup fee live.
- **Missing:** Enterprise **MSA**, **DPA**, **SLA with uptime credits**, **support tiers**, **order forms**, finalized enterprise pricing. **Counsel sign-off is pending on everything.**
- **Also need:** Cyber-liability / E&O insurance (buyers ask), selling-entity/tax structure for cross-border (VAT/GST), and **live Razorpay keys** (gated on KYC).

---

## 5. Operational readiness to *run* a regulated SaaS

This is under-built and will surface in the first security review:
- **Observability/alerting/uptime monitoring** — deferred (no Sentry/Grafana wired in prod).
- **Status page** — deferred (enterprises require one).
- **DR/BCP with stated RTO/RPO + a *tested* restore** — Cloud SQL PITR exists, but no tested restore runbook.
- **24×7 on-call + support tiers** — not defined.
- **Audit-log retention + WORM** policy; **key-rotation schedule / HSM custody** documented.
- **Real-client-IP rate limiting** behind the Cloudflare Worker (forward `CF-Connecting-IP`) — currently the unauth fallback sees the Worker's IP.

---

## 6. Product gaps that specifically block regulated adoption

Ranked by deal-impact (all are code):
1. **SSO/SCIM** — OIDC verify exists, but **no SCIM provisioning** and **no enterprise RBAC/team-invite UI**. Enterprises require both.
2. **AI Gateway BYO path doesn't enforce PII masking or budget** — for an *AI governance* product, an ungoverned passthrough is a credibility hole. Also: streaming 400s; no Azure/Anthropic shims.
3. **PII masking is regex-only** — no `MaskingPort`, no Cloud DLP/Comprehend. Regulators consider regex brittle; this is a known objection.
4. **Provable erasure** — `InMemoryShredKeyring` instead of HSM-backed `GcpKmsShredKeyring`. "Provable crypto-shred" is a DPDP/GDPR selling point you can't yet *prove*.
5. **SIEM fan-out** — only in-memory/logging sinks; **Pub/Sub / EventBridge adapters not built.** Enterprises mandate Splunk/Chronicle integration.
6. **Audit/ledger export** (CSV/JSON + proof-download) in the console — missing.
7. **AWS parity** — Bedrock, AWS KMS signer, Cognito, Step Functions all *specified, none built*. Blocks AWS-first buyers and AWS Marketplace.
8. **Auto-subscription billing** — Business/Enterprise are consultation-led; tier never auto-flips; annual renewal manual.
9. Console hygiene a CISO will flag: **self-host fonts** (currently Google CDN — IP leak for a sovereignty product), **CSP/security headers**, WCAG AA contrast, responsive pass.

---

## 7. GTM resources to actually close & serve deals

- **★ A design partner / reference customer** — you have none, and **for regulated sales this is the #1 multiplier.** The first logo (even a pilot) drives the case study, validates the residency/region choice, and de-risks every subsequent deal. Land one *now*, ideally in your beachhead regime.
- **Sales-engineering collateral:** security whitepaper, architecture one-pager, **compliance matrix** (your regime → kernel layer mapping), a stable demo environment.
- **Marketplace listings:** GCP Marketplace (metering scaffold needs the `gcp_sender` Service Control seam + a scheduler finished), AWS Marketplace (needs AWS parity), Azure.
- **Localization** of the console if selling to non-English regulators.
- **Partner/SI channel** for regulated verticals (the usual route into banks).

---

## TOP 5 critical-path blockers to the *first* regulated sale

1. **Commission the K·02 crypto review today.** 6–8 wk, longest pole, and it's the anchor of your entire credibility story.
2. **Start the SOC 2 clock (Type I now → Type II) + book an independent pen-test.** The observation window is calendar time you cannot buy back.
3. **Counsel-signed legal pack: MSA + DPA + SLA + privacy** — and immediately **rotate the leaked secrets** and clear Razorpay KYC for live keys.
4. **Land one design partner in a single beachhead regime (India or EU).** It picks your region, residency, and policy-pack priorities for you — and becomes the reference that unlocks the rest.
5. **Operational hardening to run it for real:** observability + alerting, status page, tested DR with stated RTO/RPO, on-call, and real-client-IP rate limiting.

**Sequencing note:** items 1–3 are mostly *human/process with long lead times* — they should run **in parallel, starting now**, while engineering closes the regulated product gaps in §6 (SSO/SCIM, masking port, provable erasure, SIEM fan-out). Don't let the (largely finished) code work crowd out the compliance clock — that clock is your real critical path.
