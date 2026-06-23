# Wave 3 — Legal / commercial pack tracker

> The counsel- and business-gated items from `ACTION_TRACKER.md` Wave 3. Like the Wave 2 compliance
> clocks, these are **human/process** — an agent can draft starters to brief counsel (done, linked
> below) but cannot engage counsel, buy insurance, file tax structure, or pass KYC. This is the single
> place to watch them. Starter artifacts live in `docs/legal/`.

_Last updated: 2026-06-23 · Source of truth for status: update here as items move._

## The items
| Item | ID | Lead | Owner | Status | Next concrete action | Artifact |
|---|---|---|---|---|---|---|
| **Enterprise MSA** | W3-1 | wks (counsel) | [counsel] | Starter drafted | Counsel drafts binding MSA from skeleton; resolve insurance + entity blockers | `MSA_STARTER.md` |
| **DPA** | W3-2 | — | [counsel] | **Satisfied-by** W2-5 starter | Counsel finalizes the Art.28 DPA + SCCs | `DPA_ART28_STARTER.md` |
| **SLA + uptime credits** | W3-3 | wks | [business+counsel] | Starter drafted (numbers bracketed) | Ops sets `[N]%` once W4-1/2/3 land; counsel reviews credits | `SLA_STARTER.md` |
| **Support tiers + order forms + pricing** | W3-4 | wks | [business+counsel] | Starter drafted | Business sets support targets + list pricing; reconcile with `content.ts` | `ORDER_FORM_AND_PRICING.md` |
| **Terms/Privacy/Refund sign-off** | W3-5 | wks | [counsel] | Inventory drafted — **banner stays** | Counsel works the checklist; only then remove the draft banner in a separate PR | `TERMS_SIGNOFF_INVENTORY.md` |
| **Cyber-liability / E&O insurance** | W3-6 | wks | [business] | Not started | Get quotes; bind cover — **its limits feed the MSA liability cap (clause 12)** | — |
| **Selling-entity / cross-border tax (VAT/GST)** | W3-7 | wks | [business+tax] | Not started | Decide selling entity + tax structure — **gates MSA governing-law/fees + Terms §9 + cross-border quoting** | — |
| **Live Razorpay keys** | W3-8 | KYC-gated | [business] | Not started | Complete Razorpay KYC; swap to live keys. ⚠ Also provision the **absent `RAZORPAY_WEBHOOK_SECRET`** (flagged in W0-2 — webhook signature verification may be silently off) | — |

## Dependency order (what unblocks what)
1. **W3-6 (insurance) + W3-7 (entity/tax)** are upstream blockers — the MSA can't finalize its
   **liability cap** (needs insurance limits) or **governing-law/fees** (needs the entity) without them.
   Start these two first even though they have no draft doc.
2. **W3-1 MSA** then assembles, incorporating the SLA / DPA / Order-Form exhibits (all drafted).
3. **W3-5 sign-off** can run in parallel; the draft banner comes off only after the checklist is clear.
4. **W3-8 (live keys)** is independent (KYC timeline) but needed before taking real ₹ payments — pair
   it with provisioning `RAZORPAY_WEBHOOK_SECRET`.

## Notes
- Pricing across all artifacts mirrors the live console (`console/src/legal/content.ts`): Starter
  ₹10,000/yr, ₹50,000 consultation deposit, GST exclusive, Razorpay. Keep that file the single source
  of truth — when it changes, update the SLA/order-form/MSA references.
- Nothing here removes or finalizes binding legal text; counsel originates the contracts. The starters
  exist to compress drafting time, not to replace review.
