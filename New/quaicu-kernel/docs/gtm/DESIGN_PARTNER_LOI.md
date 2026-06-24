# Design-Partner Letter of Intent / Pilot Agreement — starter outline

> **DRAFT — NOT LEGAL ADVICE.** This is an engineering/GTM-side outline of the terms a design-partner
> Letter of Intent (or short pilot agreement) should cover, to **brief counsel and speed drafting** — it
> is **not** a contract and must be drafted/reviewed by qualified counsel before signature. Cross-refs:
> `DESIGN_PARTNER_PROGRAM.md` (program), `PILOT_USE_CASES.md` (scope), `docs/legal/MSA_STARTER.md` +
> `docs/legal/DPA_ART28_STARTER.md` + `docs/legal/ORDER_FORM_AND_PRICING.md` (the binding docs counsel
> finalizes for conversion).

_Owner: [counsel] · Tracks `ACTION_TRACKER.md` W7-1 · Last updated: 2026-06-25 · Status: starter, pre-counsel_

---

## 0. Parties & nature

- **QUAICU** ([selling entity — TBD; see ACTION_TRACKER W3-7]) and **[Partner legal name]** ("Partner").
- This is a **non-binding LOI** expressing intent to run a time-boxed design-partner pilot, **except** the
  clauses expressly stated to be binding (confidentiality, data handling, IP, no-charge, term/termination).
  [Counsel decides binding vs non-binding per clause.]

## 1. Pilot scope

- **Use-case:** one of — credit-underwriting assist (HITL-gated) · KYC/AML onboarding · govern an existing
  GenAI app via the AI Gateway (`PILOT_USE_CASES.md`). State the chosen one.
- **Environment:** [SaaS — India/EU region | Model-B customer-hosted single-tenant]. State the deployment
  model, as it changes the data-transfer analysis.
- **In scope:** the governed flow, the configured RBI/DPDP policy pack, the HITL approvals path, and the
  K·02 ledger seal + regulator-verifiable proof export for the chosen use-case.
- **Out of scope:** production SLA/uptime commitments (this is a pilot), use-cases other than the one chosen,
  and any representation that QUAICU renders the Partner compliant (see §8).

## 2. Term

- **Pilot term:** **4–6 weeks** from kickoff, extendable once by mutual written agreement.
- **Phases/gates** per `DESIGN_PARTNER_PROGRAM.md` (qualify → LOI → build/shadow → run/live → inspect →
  convert).
- Either party may terminate for convenience on **[N] days'** written notice; data-return/deletion (§5) and
  confidentiality survive.

## 3. Mutual obligations

**QUAICU will:** provide the kernel for the pilot at **no platform charge**; assign a named engineer;
configure the policy pack; support the integration; and produce a regulator-verifiable proof bundle.

**Partner will:** name an **executive sponsor**, a **HITL approver**, and an **audit/risk reviewer**;
provide the real (or realistically-shaped) use-case and necessary access; join the **weekly checkpoint**;
provide **structured feedback**; and, on success, **inspect a proof bundle** and act as a **reference**
(§7). Partner supplies and pays for its own model/infra (its LLM provider keys, its KMS).

## 4. Fees

- **No platform fee during the pilot.** The standard **₹50,000 consultation deposit** is **[waived | credited
  100% against the first conversion order]** for this design partner (`DESIGN_PARTNER_PROGRAM.md` →
  *Relation to the consultation deposit*). State which.
- Partner bears its own third-party model/infra costs.

## 5. Data handling & sovereignty

- **Roles:** Partner is **controller**, QUAICU is **processor**; processing is on Partner's documented
  instructions (its configured policies + this LOI). The binding **DPA** is finalized by counsel for
  conversion (`docs/legal/DPA_ART28_STARTER.md`).
- **Data minimisation:** PII is **masked before transmission** to any model (`MaskingPort`); the Partner's
  model provider receives masked payloads.
- **Sovereignty:** **Model-B (customer-hosted, customer-held KMS)** or an **India/EU-region SaaS** deployment
  keeps data in-region; the ledger is signed by the Partner's own KMS where Model-B is used. State the model.
- **Residency / cross-border:** if any personal data would leave India/EEA, attach the appropriate transfer
  mechanism [counsel]; reference `docs/operations/DATA_RESIDENCY.md`.
- **Return/deletion at term end:** on termination, Partner data is **deleted** (default) or returned per
  Partner instruction; the crypto-shred erasure path (`core/erasure/`) makes deletion provable.
- **Security posture:** reference `SECURITY.md` + `docs/compliance/CAIQ_SIG_ANSWERS.md`; note the
  Waves 2–3 assurance items (SOC 2 / pen-test / DPA) that are **in progress**, not complete.

## 6. Intellectual property

- **Background IP** stays with its owner: QUAICU owns the kernel and any improvements; Partner owns its data,
  models, and business logic.
- **Feedback license:** Partner grants QUAICU a perpetual, royalty-free license to use **feedback** to
  improve the product (without identifying Partner). Roadmap items built from Partner feedback are QUAICU IP.
- **Partner data is never training data** for QUAICU or any third-party model beyond serving the pilot.
- The **proof bundle** generated on Partner data belongs to the Partner.

## 7. Reference & publicity rights (the W7-1 payoff)

- On a successful pilot, Partner agrees to act as a **reference** — a reference call for prospects and a
  **quote / case study**, **named or anonymised at Partner's election**.
- **Logo use** and any press are **opt-in**, separately approved in writing.
- Ideally, Partner's audit/risk reviewer confirms (named or anonymised) that the **proof was inspected** —
  the single most valuable artifact for the next buyer's security review.

## 8. Disclaimers & no compliance warranty

- QUAICU is an **enforcement + evidence control plane**; it **does not, by itself, make Partner compliant**
  with RBI FREE-AI, DPDP, or any regulation. It enforces the policies Partner configures and produces
  tamper-evident evidence. Partner remains responsible for its own regulatory compliance and obtaining its
  own legal advice. (Mirrors the governance-≠-compliance disclaimer in `docs/legal/MSA_STARTER.md`.)
- Pilot is provided **"as is"** with no production SLA; liability is limited per the binding agreement
  [counsel — typically capped at fees, which are ₹0 here, so address pilot-specific liability expressly].

## 9. Conversion path

- At pilot end, conversion to production is on the standard **quote-based MSA + order form**
  (`docs/legal/MSA_STARTER.md`, `docs/legal/ORDER_FORM_AND_PRICING.md`), with **preferential first-year
  pricing locked at pilot start** and the consultation deposit credited per §4. Target ACV **$75k–$150k+**.
- No obligation to convert — but a successful inspected pilot is the intended outcome for both sides.

## 10. Signatures

- QUAICU: __________________  ·  Partner (exec sponsor): __________________  ·  Date: __________
- Named HITL approver: __________  ·  Named audit/risk reviewer: __________

---

> **Reminder:** counsel finalizes the binding MSA + DPA + order form for conversion. This LOI exists to
> start the pilot fast with the obligations and reference rights that make W7-1 a *reference*, not just a logo.
