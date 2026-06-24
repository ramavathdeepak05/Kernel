# Design-Partner Target Profile & Outreach Kit — India regulated FS

> **Purpose:** the **ICP firmographics, qualifying questions, pitch narrative, and outreach templates** the
> team uses to source a W7-1 design partner. This names **segments and firmographics, not specific
> companies** — the team supplies the actual logos. Grounding: `docs/strategy/MARKET_2026_2027.md` (ICP,
> positioning). Program: `DESIGN_PARTNER_PROGRAM.md` · use-cases: `PILOT_USE_CASES.md` · LOI:
> `DESIGN_PARTNER_LOI.md`.

## 1. Ideal Customer Profile (firmographics — not named companies)

**Region / regime:** India, **RBI-regulated** financial services (DPDP applies across).

**Segments (priority order):**
1. **NBFCs / digital lenders** — consumer/SME lending, BNPL, co-lending. Sharpest fit for Use-case 1
   (underwriting assist) — RBI FREE-AI model-risk pressure + active GenAI experimentation.
2. **Fintechs with a lending or onboarding stack** — neobanks, lending marketplaces, embedded-finance
   players. Fit for Use-case 2 (KYC/AML) and Use-case 3 (govern an existing GenAI feature).
3. **Insurers / insurtech** — underwriting, claims triage, onboarding. Fit for Use-case 1 / 2.
4. **(Lower priority for a *first* pilot)** small private/SFB banks — heavier procurement; revisit post-reference.

**Firmographic filters:**
- **Size:** mid-market — large enough to carry a real RBI/DPDP obligation, **small enough to lack a platform
  team that would build this in-house** (the ICP wedge from the strategy). Rough band: a few hundred to a few
  thousand employees; a recognizable regulated entity, not a pre-seed startup.
- **AI maturity:** **already shipping or actively piloting GenAI / agents** — this is the single most
  important filter. It turns one of the three use-cases into *live pain*, not a hypothetical, and de-risks
  the "agents aren't in prod yet" objection.
- **Regulatory exposure:** a concrete RBI FREE-AI (model-risk, ex-post accountability) and/or DPDP
  (consent, erasure, localization) obligation they must be able to **evidence**.
- **Cloud posture:** running on a major cloud (GCP/AWS/Azure) — all governed by the neutral gateway — and/or
  a data-localization requirement that favors Model-B / in-region deployment.

**Buying committee (from the strategy):**
- **Economic buyer:** CRO / Chief Credit Officer (lending) or CCO / Head of Compliance (onboarding).
- **Gatekeeper:** CISO / DPO — must bless data handling and the security posture.
- **Champion:** the AI / platform / data-science engineer who owns the GenAI feature or the agent.

## 2. Qualifying questions (BANT-ish for regulated AI)

Use these on the first call to confirm fit and pick the use-case:

- **Pain / use-case:** "Where are you using — or about to use — an LLM or agent in a regulated workflow
  (underwriting, onboarding/KYC, a customer-facing GenAI feature)?" → maps to use-case 1 / 2 / 3.
- **Production reality:** "Is it in production, in pilot, or on the roadmap?" (Live or piloting = qualified.)
- **The governance gap:** "Today, how do you prove to RBI / your auditor *what* the AI did, under which
  policy, and who approved it?" (If the answer is "we can't / logs" — that's the wedge.)
- **Regulatory driver:** "Which obligation is forcing the timeline — RBI FREE-AI model-risk, DPDP consent/
  erasure, localization?" (Confirms a real deadline.)
- **Authority (sponsor):** "Who owns this outcome, and can they assign a person to approve decisions and a
  risk/audit person to review the evidence?" (Confirms the exec sponsor + approver + audit reviewer the
  program needs.)
- **Need (data handling):** "Does customer data have to stay in India / never leave your cloud?" (SaaS-India
  vs Model-B; surfaces the sovereignty story.)
- **Timing:** "If a pilot showed gate + seal + verifiable proof on your use-case in 4–6 weeks, could you run
  it on a real workload now?"

A qualified design partner answers: a **live/piloting** regulated AI use-case, a **provable-evidence gap**, a
**real RBI/DPDP driver**, and a **sponsor who can commit an approver + an audit reviewer**.

## 3. Pitch narrative (proof + enforcement)

**One-liner:** *"Don't just observe your AI. Govern it — and prove it."*

**The arc (60 seconds):**
1. **The shift:** AI is moving from advisory chatbots to **read-write agents** — the risk flips from
   *hallucination* to *unauthorized execution*. (MCP standardized in 2025; agent identity is 2026's top
   identity-security priority.)
2. **The gap:** GRC tools document models but are **blind at runtime**; observability tools watch but
   **don't gate**; prompt firewalls secure the prompt but **don't govern actions or produce verifiable
   audit**; hyperscaler guardrails work but **lock you in**.
3. **QUAICU:** a **fail-closed** control plane that enforces policy on AI **actions** (evaluate → gate →
   HITL → execute) and **seals every decision to an offline-verifiable RFC-6962 ledger** — **neutral** across
   clouds/models, **sovereign** (your KMS). The moat: **mathematical proof of what the AI did, under which
   policy, approved by whom.**
4. **The timing:** **RBI FREE-AI** (model-risk + ex-post accountability) and **DPDP** (consent, erasure,
   localization) are landing now — India is the 2026 beachhead; the kernel already ships the RBI/SEBI + DPDP
   policy packs.
5. **The ask:** a **4–6 week, fee-waived design-partner pilot** on one of three use-cases, ending in a
   **proof bundle your auditor can verify offline.** (`DESIGN_PARTNER_PROGRAM.md`)

**Proof points to lead with:** the offline-verifiable proof bundle (the moat); model/cloud neutrality
(OpenAI/Azure/Anthropic/Vertex/Bedrock, all governed); the RBI/DPDP packs; the HITL gate (de-risks
"agents in prod"). **Don't oversell:** QUAICU enforces + evidences; it doesn't make them compliant by itself,
and SOC 2 / pen-test / DPA are in progress (Waves 2–3).

## 4. Outreach templates

> Personalize the brackets. Keep cold notes to ~120 words. Lead with the *governance/proof gap*, not features.

### 4a. Warm intro (via a mutual contact)

> Subject: Intro — governing & proving AI decisions for [Partner]
>
> Hi [Name], thanks to [Mutual] for the intro. We built QUAICU — a control plane that lets a regulated lender
> use AI in workflows like underwriting or KYC **with a human gate and a cryptographic, regulator-verifiable
> record of every decision** (what the AI did, under which policy, who approved it). With **RBI FREE-AI** and
> **DPDP** landing, we're running a small number of **fee-waived 4–6 week design-partner pilots** with Indian
> FS teams already using GenAI. Given [Partner]'s [specific AI initiative], would a 30-min call to see if one
> of our three pilot use-cases fits be worth it? Happy to show a 10-minute "governed → sealed → verify-offline"
> demo.

### 4b. Cold exec (CRO / CCO / CISO)

> Subject: Proving what your AI decided — for RBI / DPDP
>
> Hi [Name], if [Partner] is using (or piloting) AI in underwriting, onboarding/KYC, or a customer-facing
> GenAI feature, here's the question your auditor will ask: **can you prove what the AI did, under which
> policy, and who approved it?** QUAICU is a fail-closed governance layer that puts a **human approval gate**
> on high-risk AI actions and **seals each decision to an offline-verifiable ledger** — neutral across your
> cloud/model, and your data/keys stay with you. We're selecting **1–2 India FS design partners** for a
> **fee-waived 4–6 week pilot** that ends with a **proof bundle your risk team can verify**. Worth 30 minutes?

### 4c. SI / consulting co-sell (EY / PwC / Deloitte / KPMG and regional SIs)

> Subject: Audit-grade AI governance for your FS clients (free Auditor View)
>
> Hi [Name], your FS clients are being pushed by **RBI FREE-AI** and **DPDP** to govern and *evidence* their
> AI decisions. QUAICU is the runtime control plane that enforces policy on AI actions and produces a
> **cryptographically verifiable audit bundle** an auditor can check **offline** — neutral across clouds and
> models. We'd like to give your team a **free Auditor View** so that when you advise or audit a bank's AI
> program, QUAICU is the evidence layer you can recommend. Could we explore a co-sell on one regulated-FS
> account where you'd run a joint design-partner pilot? (Ties to W7-5 — the SI channel.)

## 5. Sourcing channels (where to find the firmographics above)

- RBI-regulated-entity lists (NBFC registry) cross-referenced with **public GenAI activity** (job posts for
  "LLM/ML engineer," press on AI launches, conference talks).
- India fintech/AI events and RBI/DPDP compliance forums (the buying committee attends).
- Warm intros via investors with India FS/infra theses (the strategy names Peak XV / Lightspeed /
  Cyberstarts) and via SI partners (§4c).
- Inbound from the "AI Action Governance" category content (W7-2 collateral, once live).

> **Reminder:** this is the *framing*, not a contact list. The team supplies the specific companies and
> names; this kit makes sure every one of them is qualified against the ICP and pitched on **proof +
> enforcement**, consistent with the consultancy-led strategy.
