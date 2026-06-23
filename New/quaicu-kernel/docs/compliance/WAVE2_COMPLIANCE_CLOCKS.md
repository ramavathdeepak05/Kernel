# Wave 2 — Compliance clocks tracker

> The calendar-bound, human/process items the readiness review (`REVIEW_FINDING.md` §1) calls the
> **real critical path**: certifications and attestations whose clock time can't be compressed, so they
> must be **started in parallel now** while engineering closes product gaps. This is the single place to
> watch them. Code deliverables live in `ACTION_TRACKER.md`; this tracks the human commissioning.

_Last updated: 2026-06-23 · Source of truth for status: update here as items move._

## The clocks
| Item | ID | Lead time | Owner | Status | Next concrete action | Artifact |
|---|---|---|---|---|---|---|
| **K·02 ledger crypto review** | W2-1 | 6–8 wk (longest pole) | [eng/sec] | RFQ finalized — **send now** | Fill budget/contacts/`[TAG]`; request quotes from 2–3 firms | `docs/operations/CRYPTO_REVIEW_RFQ.md` |
| **SOC 2** (Type I → Type II) | W2-2 | 3 mo → 6–12 mo window | [compliance] | Not started — **start clock** | Engage an auditor; scope Type I; begin the Type II observation window | — |
| **Independent pen-test** | W2-3 | 3–5 wk | [security] | SoW drafted — **book** | Fill RoE/dates; send SoW to 1–2 firms | `docs/compliance/PENTEST_SOW.md` |
| **ISO 27001 (+27701)** | W2-4 | 6–12 mo | [compliance] | Not started | Select a certification body; gap assessment; build the ISMS | — |
| **GDPR Art.28 DPA + SCCs** | W2-5 | weeks (counsel) | [counsel] | Starter drafted — **to counsel** | Counsel drafts binding DPA; publish sub-processor list | `docs/legal/DPA_ART28_STARTER.md` |
| **RBI/SEBI mapping + policy pack** | W2-6 | wks (mapping) | [compliance/eng] | **Pack built ✅** — mapping doc pending | Map licence-category requirements; adapt pack to data; backtest+activate | `docs/policy-packs/rbi/` |
| **PCI-DSS SAQ-A** | W2-7 | confirm | [compliance] | Scope memo drafted — **confirm** | Pull provider AoCs; confirm SAQ-A with acquirer/QSA; sign SAQ-A | `docs/compliance/PCI_SAQ_A_SCOPE.md` |
| **HIPAA BAA** | W2-8 | weeks | [counsel] | **Deferred** (only if healthcare) | — | — |

## Sequencing (from REVIEW_FINDING.md TOP-5)
1. **Commission the crypto review today** — longest pole, anchors the credibility story.
2. **Start the SOC 2 clock + book the pen-test** — observation/scheduling time you can't buy back.
3. **Counsel-signed legal pack** (DPA/SCCs here; MSA/SLA are Wave 3).
4. Land a design partner in one beachhead regime (Wave 7) — it picks which of these to prioritise.
5. Operational hardening (Wave 4).

> **Don't let finished code crowd out the clock.** Waves 2–3 are mostly human/process with long lead
> times; engineering closing Wave 6 product gaps does **not** advance these. Run them concurrently.

## Beachhead note
Per the readiness review, **India (RBI/DPDP)** or **EU** is the natural first beachhead (Razorpay live,
DPDP/EU packs shipped). Picking one lets you sequence the certifications by what that regime gates
first — e.g. India-first leans on the RBI/SEBI pack + DPDP + data localization; EU-first leans on the
Art.28 DPA + SCCs + ISO 27701 + an EU-region deployment (W5).
