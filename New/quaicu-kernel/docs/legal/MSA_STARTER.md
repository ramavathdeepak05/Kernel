# Master Services Agreement (MSA) — starter outline

> **DRAFT — NOT LEGAL ADVICE.** This is an engineering/commercial-side skeleton of the clauses an
> enterprise MSA needs, with notes on where QUAICU's product reality should fill each in. It exists to
> **brief counsel and speed drafting** — it is not a contract and must be drafted and reviewed by a
> qualified lawyer (Indian counsel as primary, with local counsel for EU/Gulf deals) before use.

_Owner: [counsel] · Tracks ACTION_TRACKER **W3-1** · Last updated: 2026-06-23_

## Context
The MSA is the master contract a customer signs once; per-purchase commercial terms go on an **Order
Form** (see `ORDER_FORM_AND_PRICING.md`), data terms go in the **DPA** (`DPA_ART28_STARTER.md`), and
uptime terms in the **SLA** (`SLA_STARTER.md`). The MSA references those as incorporated exhibits.

Contracting entity (from `console/src/legal/content.ts`): **QUAICU Solutions Private Limited**,
T-Hub, Hyderabad, Telangana, India. Confirm the actual selling entity per W3-7 (a cross-border deal
may sell from a different entity for tax reasons).

## Structure (MSA + exhibits)
```
MSA (this doc)
├── Exhibit A — Order Form(s)            → ORDER_FORM_AND_PRICING.md
├── Exhibit B — Service Level Agreement  → SLA_STARTER.md
├── Exhibit C — Data Processing Addendum → DPA_ART28_STARTER.md (+ SCCs)
└── Exhibit D — Support Policy           → ORDER_FORM_AND_PRICING.md §Support tiers
```

## Clause checklist (and QUAICU's posture)
| # | Clause | Drafting note / product reality |
|---|--------|---------------------------------|
| 1 | **Definitions** | Define "Service", "Kernel", "Tenant", "Governed Action", "Audit Ledger", "Customer Data", "Deployment Model" (Model A shared SaaS plane vs Model B customer-hosted single-tenant — this distinction recurs throughout). |
| 2 | **Provision of the Service / licence grant** | Non-exclusive, non-transferable right to access the governance kernel + console for the subscription term, scoped to the tenant(s) on the Order Form. |
| 3 | **Order Forms & priority of documents** | Order Form > SLA/DPA exhibits > MSA body. State that exhibits are incorporated by reference. |
| 4 | **Fees, invoicing, taxes** | Mirror the live pricing: Starter ₹10,000/yr at signup + renewal; Business/Enterprise quote-based with a ₹50,000 consultation deposit. Amounts exclusive of GST/applicable taxes. Payment via Razorpay. Cross-ref Refund Policy for non-refundability. |
| 5 | **Term & renewal** | Subscription term + auto-renewal (annual). Note: auto-renewal billing is **not yet automated** in product (W6-8 is manual/consultation-led) — keep renewal contractual, not a claim of auto-charge, until W6-8 ships. |
| 6 | **Customer obligations / acceptable use** | Lawful use, no probing other tenants, accurate KYC info, responsibility for their configured policies and their end-users. Tie to the Terms of Service (`content.ts` Terms). |
| 7 | **Confidentiality** | Mutual; standard carve-outs; survival. |
| 8 | **Data protection & security** | Point to the DPA (Exhibit C) for processing terms and to the security-measures annex (SOC 2 / ISO 27001 evidence once available — Wave 2/4). Don't restate Art.32 measures here; reference them. |
| 9 | **IP ownership** | QUAICU owns the platform/IP; customer owns Customer Data; QUAICU may use aggregated, de-identified operational metrics. Be explicit that the **audit ledger entries are the customer's records** but the ledger *mechanism* is QUAICU IP. |
| 10 | **Warranties** | Service performs materially per docs; each party has authority. **Disclaim** beyond the express warranty. The kernel is **fail-closed governance, not a guarantee of regulatory compliance** — the customer is responsible for the legality of their own policies/decisions. State this plainly (it is the single most important risk allocation for a governance product). |
| 11 | **Indemnification** | QUAICU IP-infringement indemnity (mutual-ish); customer indemnity for its data/use. Carve K·02/governance "compliance outcome" claims out of QUAICU's indemnity per clause 10. |
| 12 | **Limitation of liability** | Cap (e.g. fees paid in trailing 12 months); exclude indirect/consequential. Coordinate the cap with the **cyber/E&O cover** (W3-6) so the cap is actually insured. |
| 13 | **Service levels & credits** | Reference the SLA (Exhibit B). Service credits are the **sole remedy** for downtime. |
| 14 | **Term suspension & termination** | For cause / non-payment / AUP breach; effect of termination; **data export + deletion** on exit (ties to DPA (g) — crypto-shred erasure path, W6-4). |
| 15 | **Sub-processors** | Reference the DPA sub-processor list (Razorpay, Resend, Google Cloud, Cloudflare) + change-notice mechanism. |
| 16 | **Insurance** | State the cyber-liability / E&O cover the company carries (W3-6 — get the binder first, then fill the limits here). |
| 17 | **Governing law / dispute resolution** | Default: India (entity is in Hyderabad) — confirm with W3-7. For EU/Gulf customers expect pushback; have a fallback (e.g. arbitration seat) ready. |
| 18 | **Force majeure, assignment, notices, severability, entire agreement** | Standard boilerplate; align "notices" with support@quaicu.org + the registered address. |

## Open dependencies (don't sign around these)
- **Liability cap ↔ insurance (W3-6):** set the cap only once the cyber/E&O limits are known.
- **Selling entity / governing law (W3-7):** the entity and law clauses depend on the tax/entity decision.
- **Auto-renewal (clause 5):** keep contractual until billing automation (W6-8) is live; don't promise auto-charge the product can't do yet.
- **Compliance disclaimer (clause 10):** this must survive review intact — it is what keeps QUAICU a *tooling* vendor, not a *compliance guarantor*.

## Next actions
1. Counsel drafts the binding MSA from this skeleton + the company's standard template.
2. Resolve the two blockers above (insurance limits, selling entity/governing law).
3. Wire the four exhibits (Order Form, SLA, DPA, Support Policy) as incorporated attachments.
4. After counsel sign-off, this unblocks removing the "draft" banners on the public Terms (see
   `TERMS_SIGNOFF_INVENTORY.md`, W3-5).
