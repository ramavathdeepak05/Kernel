# QUAICU Design-Partner Program

> **Goal:** land **one inspected reference customer** in India regulated FS — the strategy's #1 GTM
> multiplier (`ACTION_TRACKER.md` W7-1; `docs/strategy/MARKET_2026_2027.md` §6.2). Success is **not** a
> logo or a signature — it is a **reference whose audit/risk team has inspected the proof** and will say so.
> Use-cases: `PILOT_USE_CASES.md` · LOI: `DESIGN_PARTNER_LOI.md` · who to approach: `TARGET_LIST_AND_OUTREACH.md`.

## What this is

A time-boxed (**4–6 week**) co-development pilot with a small number of design partners (target: **1–2**),
each running **one** of the three curated use-cases (`PILOT_USE_CASES.md`). We waive the fee in exchange for
a real use-case, exec sponsorship, structured feedback, and — on success — a reference the next buyer's
security review will trust. It is the bridge from "engineering is ahead of market validation" (the strategy's
honest bottom line) to "here is a regulated FS customer who inspected the proof and stayed."

## What the partner gets

- **A fee-waived / fee-credited pilot.** The standard engagement is the **₹50,000 consultation deposit** →
  integrations team (`delivery/docker/kernel.saas.toml [consultation]`). For a qualified design partner we
  **waive or fully credit** that deposit (see *Relation to the consultation deposit* below). No platform
  charge during the pilot window.
- **Co-development + direct founder/eng access.** A named QUAICU engineer for the pilot; the partner's
  edge cases shape the integration (e.g. the Slack/Teams fast-approve path, a provider shim, a policy-pack
  refinement).
- **Priority roadmap influence.** Design-partner-pulled work jumps the queue — consistent with the strategy's
  "build only what a design partner pulls" stance (W7-3/W7-4/W8 are explicitly gated on this).
- **The deliverable they keep:** a working governed flow on **their** use-case, the configured per-regime
  **policy pack** (RBI / DPDP), and a **regulator-verifiable proof bundle** they can hand to their own
  auditor/regulator.
- **Conversion economics:** preferential first-year pricing locked at pilot start (the conversion path is in
  the LOI), so the pilot isn't a cliff.

## What we ask in return

- **A real use-case in production-adjacent conditions** — one of the three in `PILOT_USE_CASES.md`, on real
  (or realistically-shaped) data, not a toy. The reference only matters if the workload was real.
- **A named executive sponsor + a named approver.** Sponsor = the CRO/CCO/CISO who owns the outcome; approver
  = the human who actually clicks approve/reject in the HITL queue. Both named in the LOI.
- **Weekly structured feedback** — a 30–45 min weekly checkpoint across the 4–6 weeks, plus async issue
  reporting. We capture it against the roadmap.
- **An inspection by their audit/risk/compliance function** — the heart of the deal: their team verifies a
  proof bundle and confirms it meets their evidence needs. This is what makes it a *reference*, not a logo.
- **On success: reference rights** — a reference call for future prospects, a quote/case study (named or
  anonymised per their comfort), and ideally a testimonial that the audit was inspected. Logo use is opt-in
  and negotiated separately.

## Selection criteria (who qualifies as a design partner)

A good first design partner (firmographics in `TARGET_LIST_AND_OUTREACH.md`):

1. **India RBI-regulated FS** — NBFC, digital lender, fintech, or insurer (the beachhead ICP).
2. **Already shipping or actively piloting GenAI/agents** — so one of the three use-cases is *live pain*,
   not hypothetical (de-risks the "agents aren't in prod" TAM concern).
3. **A real RBI FREE-AI / DPDP obligation** they must evidence — i.e. the proof bundle solves a problem they
   already have.
4. **An engaged exec sponsor** with authority to assign an approver and an audit reviewer.
5. **Mid-market** — large enough to have the obligation, small enough to lack a platform team that would DIY
   (the ICP wedge).

## Relation to the ₹50,000 consultation deposit

The normal motion is **consultation-led** (the strategy is explicitly *not* self-serve subscription — see
the W6-8 deferral): a prospect pays the **₹50,000 consultation deposit** to engage the integrations team;
Business/Enterprise tiers are quote-based and the tier is **not** auto-flipped. For a **design partner** we
modify this:

- **Waive or credit the deposit.** Either skip it (fee-waived pilot) or take it and **credit 100% against the
  first conversion order** (fee-credited) — finance picks per partner. The LOI states which.
- The pilot itself carries **no platform charge**; the partner pays only their own model/infra costs (their
  OpenAI/Anthropic/Vertex/Bedrock keys, their KMS).
- **Conversion** at pilot end follows the standard quote-based **MSA + order form** path
  (`docs/legal/MSA_STARTER.md`, `docs/legal/ORDER_FORM_AND_PRICING.md`), with the preferential first-year
  pricing the LOI locks in. ACV target per the strategy: **$75k–$150k+**.

## Timeline & gates

| Phase | Duration | Gate to advance |
|-------|----------|-----------------|
| Qualify | ~1 wk | Meets selection criteria; exec sponsor named; use-case chosen |
| LOI / kickoff | ~1 wk | LOI signed (`DESIGN_PARTNER_LOI.md`); approver + audit reviewer named; data-handling model agreed (SaaS-EU/India vs Model-B) |
| Build (shadow) | wk 1–2 | Use-case connected; policy pack loaded in **shadow mode**; backtest reviewed |
| Run (live, bounded) | wk 2–4 | Live on a bounded segment; HITL queue in use; seals accumulating |
| Inspect | wk 5–6 | **Proof bundle inspected by the partner's audit/risk team** ✅ — the reference moment |
| Convert | post-pilot | MSA + order form; reference rights exercised |

## Definition of success

- **The pilot's headline use-case metric is hit** (see each use-case in `PILOT_USE_CASES.md`).
- **The partner's audit/risk/compliance team has inspected a proof bundle** and confirmed it meets their
  RBI/DPDP evidence needs.
- **The partner agrees to be a reference** (call + quote/case study, named or anonymised).
- Bonus: the partner converts to a paid MSA. (The *reference* is the W7-1 success criterion; the conversion
  is the commercial upside.)

## Risks & honesties (don't oversell)

- QUAICU is the **enforcement + evidence** layer; it does **not** by itself make the partner RBI/DPDP
  compliant — say so plainly (mirrors the legal-starter disclaimer).
- Several managed adapters (HSM-backed erasure keyring, Cloud DLP masking, Anthropic/Vertex/Bedrock shims,
  AWS Step Functions) are validated with **fake-client tests, not against live cloud APIs** — the pilot is
  where they first run against the partner's real environment. Set this expectation up front.
- The **assurance gap** (SOC 2 / pen-test / counsel-signed DPA — Waves 2–3) is the #1 deal-blocker and runs
  in parallel; a design partner can pilot before they close, but conversion to a production MSA will want
  them progressing. Have the trust-center status ready (`SECURITY.md`, `docs/compliance/CAIQ_SIG_ANSWERS.md`).
