# QUAICU Design-Partner Pilot Use-Cases — India regulated FS

> **Purpose:** the curated **3-use-case mix** a first inspected design partner can run on the QUAICU
> kernel today. Each use-case maps to **already-built** kernel surfaces (no vaporware), carries a real
> RBI/DPDP regulatory hook, and has success metrics, a demo script, and a 4–6 week pilot scope.
> Tracks `ACTION_TRACKER.md` **W7-1**. ICP & positioning: `docs/strategy/MARKET_2026_2027.md`.
> Program terms: `DESIGN_PARTNER_PROGRAM.md` · LOI: `DESIGN_PARTNER_LOI.md` · targets: `TARGET_LIST_AND_OUTREACH.md`.

## Why three (not one)

The strategy memo's ICP is **India mid-market regulated FS** (NBFCs, digital lenders, fintechs,
insurers) and the category is **"AI Action Governance" — sell proof + enforcement, not dashboards.**
Rather than bet the first reference on a single vertical, we offer a curated mix spanning the kernel's
three strongest stories at three friction levels, so a partner can self-select the one that matches
where their AI actually is today:

1. **Credit-underwriting assist (HITL-gated)** — the flagship *action-governance* story; medium friction.
2. **KYC/AML onboarding** — the *data-protection* story (DPDP); higher friction, deepest reg pull.
3. **Govern an existing GenAI app via the AI Gateway** — the *lowest-friction wedge*; one base-URL change.

All three end the same way: **a fail-closed gate + an offline-verifiable RFC-6962 ledger seal** — the moat.
(Deliberately excluded from the first pilot: **collections / customer-comms** agents — higher reputational
and conduct risk for a first reference. Noted as a **phase-2 expansion** once the reference is inspected.)

---

## Summary table

| # | Use-case | Friction | Primary regime | Core kernel surface (built) | Headline success metric |
|---|----------|----------|----------------|------------------------------|--------------------------|
| 1 | Credit-underwriting assist (HITL-gated) | Medium | RBI FREE-AI (model-risk + ex-post accountability) | `require_approval` policy → HITL approvals (`/v1/approvals`) → K·02 seal + regulator export | 100% of high-risk drafts human-approved; every decision has a verifiable proof |
| 2 | KYC/AML onboarding | High | DPDP + RBI KYC | Consent (K·04) + `MaskingPort` PII masking + crypto-shred erasure (W6-4) + DPDP policy pack | PII masked before any model call; consent recorded per decision; erasure provable |
| 3 | Govern an existing GenAI app via the AI Gateway | Low | DPDP (data minimisation) + neutrality | Governed gateway (`POST /v1/ai/chat/completions`): PII masking + per-tenant budget + sealed audit | Time-to-value < 1 day (base-URL swap); every model call masked, budgeted, sealed |

> **Reg-hook honesty note.** QUAICU is the *enforcement + evidence* control plane; it does **not** make
> the partner compliant by itself. It enforces the policies the partner configures and produces the
> tamper-evident proof a regulator/auditor can verify. The RBI/DPDP "hooks" below are the obligations the
> kernel *supports satisfying*, not a compliance certification. (Same disclaimer as the legal starters.)

---

## Use-case 1 — Credit-underwriting assist (HITL-gated)

**The flagship action-governance story.** De-risks the #1 market objection ("agents aren't in prod yet"):
the agent **drafts**, a human **approves**, and the kernel **seals** — so the partner gets AI leverage with
zero unsupervised execution.

- **Target persona + pain.** Buyer = **CRO / Chief Credit Officer**; gatekeeper = **CISO**; champion =
  the **lending / data-science lead**. Pain: they want LLM-assisted underwriting (faster decisions, richer
  narratives) but cannot let a model decide a credit line unsupervised, and RBI's FREE-AI report expects
  **model-risk management + ex-post accountability** — i.e. "who decided this, under what policy, and can
  you prove it months later?"
- **The governed flow (mapped to built surfaces).**
  1. An internal agent proposes a credit decision / limit as a **governed action** (lifecycle:
     propose → evaluate → gate → execute → seal).
  2. A CEL policy with `require_approval` routes **high-risk** drafts (e.g. above a limit threshold, thin
     file, or a policy-flagged segment) to a **human approver** — the K·08/K·05 gate is fail-closed: no
     approval, no execution.
  3. The approver acts via the **HITL approvals API** — `GET /v1/approvals` (queue),
     `POST /v1/approvals/{id}/approve` / `/reject` (the kernel enforces no self-approval, expiry, and
     single-decision). A Slack/Teams approve step is a documented integration follow-up.
  4. On execute, the decision is **sealed to the K·02 TrustLedger** (RFC-6962 Merkle, HSM/KMS-signed tree
     head). The decision input, the policy version, the model id/version, the approver identity, and the
     consent context are all in the sealed entry.
  5. A regulator/auditor later pulls a **self-verifying proof bundle** —
     `GET /v1/ledger/{tenant}/export` — and verifies it **offline** (or via `POST /v1/ledger/export/verify`),
     independent of QUAICU.
- **Regulatory hook.** RBI FREE-AI — model-risk management, human accountability for AI-assisted credit
  decisions, ex-post auditability. The proof bundle is the ex-post evidence.
- **Success metrics (what "the pilot worked" means).**
  - 100% of high-risk drafts pass through a recorded human approval (no bypass path exercised).
  - Every credit decision has an inclusion proof that verifies offline.
  - Decision turnaround time improves vs. the manual baseline while approvals stay 100%.
  - The partner's audit/risk team confirms a sampled decision is fully reconstructable from the bundle.
- **Demo script (≈10 min).** (1) Submit a low-risk draft → auto-approved by policy → sealed; show the
  ledger entry. (2) Submit a high-risk draft → it lands in `/v1/approvals` pending; show the approver
  approve/reject; show the sealed outcome carries the approver identity. (3) Export the proof bundle and
  **verify it offline** with the bundled verifier — "here's mathematical proof of what the AI did, under
  which policy, approved by whom."
- **Pilot scope (4–6 wk).** Wk 1: connect one internal underwriting agent + author the
  `require_approval` policy (start in **shadow mode** to backtest before activating). Wk 2–4: run on a
  bounded segment / shadow-then-live; wire the approvals queue to the credit team. Wk 5–6: produce a proof
  bundle for the partner's risk/audit team to inspect → the reference.

---

## Use-case 2 — KYC/AML onboarding (data-protection-heavy)

**The DPDP story.** An agent screens / onboards a new customer; humans handle edge cases; **PII is masked
before any model call, consent is recorded at decision time, and erasure is provable.**

- **Target persona + pain.** Buyer = **CCO / Head of Compliance**; gatekeeper = **DPO / CISO**; champion =
  the **onboarding / financial-crime ops lead**. Pain: they want to use models to accelerate
  KYC/AML triage but every model call risks shipping customer PII to a third-party LLM, **DPDP** demands
  purpose-bound consent and a provable erasure path, and RBI KYC requires an audit trail.
- **The governed flow (mapped to built surfaces).**
  1. The agent screens/onboards; **edge cases route to a human** via the same HITL approvals surface as
     Use-case 1 (`/v1/approvals`).
  2. **PII is masked before transmission** to any model — the `MaskingPort` (`core/ports/masking.py`):
     the default regex adapter, or the managed **Cloud DLP** adapter (catches names/addresses regex
     misses); the response is rehydrated. Masking is enforced in the gateway path, not optional best-effort.
  3. **Consent is a second evaluate-time signal** — the K·04 consent layer (`core/consent/`): a
     missing / expired / withdrawn consent for the processing purpose makes the action **DENY** (fail-closed),
     and the consent state is recorded in the ledger entry so it's point-in-time resolvable on replay.
  4. **Provable erasure** — the crypto-shred erasure engine (`core/erasure/`) with the HSM-backed
     `GcpKmsShredKeyring` (W6-4): destroying a subject's wrapped DEK makes their data unrecoverable, which is
     how you answer a DPDP erasure request with evidence rather than a promise.
  5. The **DPDP policy pack** (`docs/policy-packs/dpdp/`) supplies the starter CEL policies; the **RBI pack**
     (`docs/policy-packs/rbi/`) covers KYC access-logging / localization. Every onboarding decision is sealed
     to K·02 as in Use-case 1.
- **Regulatory hook.** **DPDP** (purpose-bound consent, data-principal erasure rights, data minimisation via
  masking) + **RBI KYC** (audit trail, access logging). Note: DPDP Rules notified Nov 2025, full
  applicability ~May 2027 — so this is **ahead of the cliff**, which is the selling point.
- **Success metrics.**
  - Zero un-masked PII leaves the tenant boundary on a model call (verified on a sampled transcript).
  - Every onboarding decision carries a recorded consent state; a withdrawn-consent case is shown to DENY.
  - An erasure request is executed and **proven** (the DEK is destroyed; the subject's data is shown
    unrecoverable).
  - The compliance team confirms the audit trail + consent record satisfies their DPDP/KYC evidence needs.
- **Demo script (≈10 min).** (1) Onboard a customer with PII in the prompt → show the masked text that
  actually hits the model + the rehydrated answer. (2) Replay with consent withdrawn → DENY, sealed as a
  denied action. (3) Run an erasure request → show the crypto-shred and that the subject is now
  irrecoverable, with the action sealed. (4) Export + verify the trail for the compliance team.
- **Pilot scope (4–6 wk).** Wk 1: enable masking (regex first; DLP if the partner wants managed
  detection) + load the DPDP/RBI packs in shadow. Wk 2–4: run onboarding triage on a bounded cohort with
  consent + HITL on edge cases. Wk 5–6: demonstrate a full erasure with proof + hand the audit trail to the
  DPO. **Note (honest):** the HSM-backed keyring and Cloud DLP are validated with fake-client tests, not
  against live GCP — the pilot is where they get exercised against the partner's real KMS/DLP project.

---

## Use-case 3 — Govern an existing GenAI app via the AI Gateway (lowest-friction wedge)

**The fastest time-to-value.** The partner *already* runs a GenAI feature (a support assistant, a doc
summariser, a chatbot). We govern its model calls through the gateway with **a one-line base-URL change** —
no new agent to build, no app rewrite.

- **Target persona + pain.** Buyer = **CISO / Head of AI**; champion = the **engineer who shipped the GenAI
  feature**. Pain: a GenAI feature is live and **ungoverned** — prompts (with customer data) go straight to
  OpenAI/Anthropic/Vertex/Bedrock, there's no spend ceiling, and there's no audit of what was sent. Security
  wants control without blocking the launch.
- **The governed flow (mapped to built surfaces).**
  1. The partner repoints their OpenAI-compatible client's **base URL** at the QUAICU governed gateway —
     `POST /v1/ai/chat/completions` (`GET /v1/ai/connection` configures the upstream).
  2. The gateway enforces, per tenant: **PII masking** before forwarding (same `MaskingPort` as Use-case 2),
     a **per-tenant token budget** (429 `BUDGET_EXCEEDED` on exhaustion — cost governance), and a **sealed
     audit** of every call to K·02. **Streaming (SSE) is supported.**
  3. **Neutrality:** the same gateway governs **OpenAI-compatible, Azure OpenAI, Anthropic, Google Vertex,
     and AWS Bedrock** (all five shims built, W6-2) — the partner keeps their model of choice; QUAICU is the
     neutral control point, not a model vendor.
- **Regulatory hook.** **DPDP data minimisation** (PII never leaves un-masked) + the neutrality/sovereignty
  story (no hyperscaler lock-in; customer-held KMS for the seal). The wedge: governance value in a day,
  which earns the right to the deeper Use-case 1/2 conversations.
- **Success metrics.**
  - **Time-to-value < 1 day** — governance live via a base-URL swap, no app changes.
  - 100% of model calls are masked + budget-checked + sealed (verified on the trail).
  - A spend cap is shown to actually stop runaway usage (budget 429).
  - The partner confirms the audit trail answers "what did our GenAI feature send to the model, and when?"
- **Demo script (≈5 min).** (1) Point a stock OpenAI client at the gateway base URL — same code, now
  governed. (2) Send a prompt with PII → show the masked upstream payload + rehydrated response. (3) Exhaust
  the budget → 429. (4) Show every call sealed in `/v1/ledger/{tenant}/trail` and export the bundle.
- **Pilot scope (4–6 wk, but value in wk 1).** Wk 1: base-URL swap + masking + budget on one GenAI feature →
  governed and sealed. Wk 2–6: optional — expand to more features / providers, and use this as the on-ramp
  to scope Use-case 1 or 2. **Note (honest):** Anthropic/Vertex/Bedrock shims are validated with fake-client
  tests, not against live provider APIs — the pilot validates the partner's actual provider end-to-end.

---

## What this kit does **not** include (follow-ups / other waves)

- **Actually contacting / signing a partner** — human; the team supplies the logos
  (`TARGET_LIST_AND_OUTREACH.md` gives the firmographics + outreach).
- **Security whitepaper, architecture one-pager, compliance matrix, stable scripted demo env** — that's
  **W7-2** (separate). This kit is the use-case + program + LOI + target framing.
- **A Slack/Teams fast-approve integration** and **verify-by-upload UI** — documented product follow-ups
  (the approvals + export APIs exist; the convenience UX is not built yet).
- **Collections / customer-comms agent** — phase-2 expansion, intentionally out of the first pilot.
