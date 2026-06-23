# Public legal docs — counsel sign-off inventory (W3-5)

> **DRAFT — NOT LEGAL ADVICE.** This is the **gate** for ACTION_TRACKER W3-5 ("counsel sign-off on
> Terms/Privacy/Refunds; remove draft banners"). It tells counsel exactly what to review and what
> removing the draft banner requires. It does **not** itself authorize removing anything.

_Owner: [counsel] · Tracks ACTION_TRACKER **W3-5** · Last updated: 2026-06-23_

## ⛔ DO NOT STRIP THE DRAFT BANNER UNTIL SIGNED OFF
The public legal text lives in **`console/src/legal/content.ts`** and opens with (lines 1–2):

```
// Legal document content (TEMPLATES). These are starting drafts — NOT legal advice. Replace the
// [PLACEHOLDERS] with your real details and have a qualified lawyer review before relying on them.
```

That banner — and any in-page "draft" markers — **must remain** until a qualified lawyer has reviewed
each document below and the entity/placeholder fields are finalized. Removing it presents un-reviewed
legal text to customers as final and binding. The banner comes off in a **separate code change**,
only after every checklist box below is ticked. This doc is read-only on the banner; it does not edit
`content.ts`.

## Documents in scope (`console/src/legal/content.ts`)
| Doc | Sections | Highest-risk clauses for legal review |
|-----|----------|---------------------------------------|
| **Terms of Service** (`:20`) | 1 Agreement · 2 The Service · 3 Accounts & security · 4 Fees & payment · 5 Acceptable use · 6 Intellectual property · **7 Disclaimers & liability** · 8 Termination · **9 Governing law** · 10 Contact | §7 disclaimer/liability cap; the **governance-is-tooling-not-compliance** disclaimer (must match MSA clause 10); §9 governing law (depends on W3-7 entity decision); §4 fees consistency with live pricing |
| **Privacy Policy** (`:86`) | 1 Who we are · 2 Data we collect · 3 How we use it · **4 Processors we use** · **5 Your rights** · 6 Retention & security · 7 Contact | §4 sub-processor list must match the DPA (`DPA_ART28_STARTER.md`): Razorpay, Resend, Google Cloud, Cloudflare; §5 DPDP + GDPR rights statements; §6 retention/security claims must match actual posture |
| **Refund & Cancellation** (`:134`) | **1 Starter annual fee (₹10,000)** · **2 Business/Enterprise consultation deposit (₹50,000)** · 3 How to cancel / request a refund · 4 Contact | Non-refundability language (§1, §2) — enforceability under Indian consumer law + Razorpay rules; must match the order-form language in `ORDER_FORM_AND_PRICING.md` |
| **Contact** (`:164`) | Get in touch · Company | Entity/address accuracy |

## Placeholders / entity fields to finalize
- `ENTITY = "QUAICU Solutions Private Limited"` (`content.ts:12`) — confirm this is the actual selling
  entity (may change per **W3-7** tax/entity decision; a different entity changes Terms §9 governing
  law + the contracting party throughout).
- `ADDRESS = "T-Hub, Hyderabad, Telangana, India"` (`content.ts:13`) — confirm registered address.
- `support@quaicu.org` — confirm this is the monitored legal/privacy contact.
- Any remaining `[PLACEHOLDER]` tokens the banner refers to.

## Cross-consistency checks (so public text ≠ contracts)
- Refund Policy §1/§2 ↔ `ORDER_FORM_AND_PRICING.md` §C and the MSA fees clause.
- Privacy §4 processors ↔ DPA sub-processor list (`DPA_ART28_STARTER.md`).
- Terms §7 disclaimer ↔ MSA clause 10 (governance ≠ compliance guarantee).
- Terms §9 governing law ↔ MSA clause 17 ↔ W3-7 entity decision.

## Sign-off checklist (all must be ticked before the banner is removed)
- [ ] Counsel reviewed **Terms of Service** (esp. §7, §9).
- [ ] Counsel reviewed **Privacy Policy** (DPDP + GDPR; processor list matches DPA).
- [ ] Counsel reviewed **Refund & Cancellation** (non-refundability enforceable; matches order form).
- [ ] **ENTITY / ADDRESS / contact** finalized (W3-7 resolved if it affects the entity).
- [ ] Public text reconciled with MSA / SLA / Order Form / DPA (no divergence).
- [ ] Effective/last-updated dates added to each public doc.
- [ ] **Then** (separate code change): remove the banner at `content.ts:1-2` + any in-page draft markers.

## Next actions
1. Counsel works top-to-bottom through the checklist.
2. Resolve W3-7 (entity) since it gates governing-law + the contracting party.
3. Only after every box is ticked, open the small PR that removes the draft banner — reference this
   doc in that PR description as the sign-off record.
