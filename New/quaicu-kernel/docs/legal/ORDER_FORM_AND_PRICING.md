# Order Form, Support Tiers & Pricing — starter

> **DRAFT — NOT LEGAL ADVICE.** A template + reference for sales/business and counsel. Pricing here
> mirrors what the live console already charges; treat anything bracketed `[…]` as a value the
> business must set. Signed, the order form is **Exhibit A** to the MSA (`MSA_STARTER.md`); support
> tiers are **Exhibit D**.

_Owner: [business + counsel] · Tracks ACTION_TRACKER **W3-4** · Last updated: 2026-06-23_

## A. Order Form template
> One per purchase; references the MSA + exhibits. The Order Form controls over the MSA body on
> conflict (per `MSA_STARTER.md` clause 3).

```
ORDER FORM — under the QUAICU Master Services Agreement dated [____]

Provider:  QUAICU Solutions Private Limited, T-Hub, Hyderabad, Telangana, India
Customer:  [legal name], [address], [registration no.]

1. Plan / Tier:        [ Starter | Business | Enterprise ]
2. Deployment model:   [ Model A shared SaaS plane | Model B customer-hosted single-tenant ]
3. Tenant(s) / seats:  [____]
4. Subscription term:  [12] months, starting [effective date]
5. Fees:               [see §C pricing] — exclusive of GST/applicable taxes
6. Payment:            Razorpay; [annual, in advance] ; net [0] days
7. Renewal:            [auto-renew for successive 12-mo terms unless notice given [30] days prior]
                       ⚠ until W6-8 (billing automation) ships, treat renewal as an INVOICE event,
                       not an auto-charge — do not promise card-on-file auto-billing the product
                       cannot yet perform.
8. SLA:                Exhibit B (SLA_STARTER.md) — uptime target [N]%
9. Support tier:       Exhibit D (§B below)
10. Special terms:     [____]

Signed: ____________________ (Provider)   ____________________ (Customer)
```

## B. Support tiers (Exhibit D)
| | **Starter** | **Business** | **Enterprise** |
|---|---|---|---|
| Channel | Email (support@quaicu.org) | Email + priority queue | Named contact / dedicated channel |
| Hours | Business hours (IST) | Business hours (IST) | [Extended / 24×7 — see W4-4] |
| First-response target | `[2] business days` | `[1] business day` | `[4] business hours` |
| Sev-1 (service down) target | `[best-effort]` | `[8] business hours` | `[2] hours]` |
| Onboarding | Self-serve | Guided | Integrations-team engagement (₹50,000 consultation) |

> ⚠ 24×7 and tight Sev-1 targets depend on an on-call rotation (**W4-4**) that does not yet exist.
> Don't sell response times the team can't staff — bracket them until W4-4 is real.

## C. Pricing sheet (mirrors the live console)
Source of truth in product: `console/src/legal/content.ts` (Refund Policy §1–2) and `console/src/api/types.ts`.

| Plan | Price | Billing | Notes |
|------|-------|---------|-------|
| **Starter** | **₹10,000 / year** | At signup + each renewal | Activates the workspace immediately; non-refundable once provisioned (Refund Policy §1) |
| **Business** | **Quote-based** | + **₹50,000 consultation deposit** | Deposit reserves integrations-team time; may be adjusted against first invoice at QUAICU's discretion (Refund Policy §2) |
| **Enterprise** | **Quote-based** | + **₹50,000 consultation deposit** | Custom SLA/support/residency on the order form |

- **All amounts exclusive of GST / applicable taxes.** Tax treatment for cross-border sales depends on
  the selling-entity/VAT-GST decision (**W3-7**) — confirm before quoting non-India customers.
- **Payments via Razorpay**; live keys are KYC-gated (**W3-8**). Today the console runs Razorpay in the
  configured mode; going live needs cleared KYC.
- The ₹50,000 consultation deposit is **non-refundable** (reserves dedicated time) per the live Refund
  Policy — keep order-form language consistent with `content.ts` so the contract and the public policy
  don't diverge.

## D. Next actions
1. Business sets the bracketed support targets + any enterprise list pricing; counsel reviews.
2. Reconcile every figure here against `content.ts` whenever public pricing changes (single source).
3. Resolve W3-7 (tax/entity) before quoting cross-border; W3-8 (KYC) before taking live ₹ payments.
4. Attach as Exhibits A + D to the MSA.
