# Service Level Agreement (SLA) — starter

> **DRAFT — NOT LEGAL ADVICE, and NOT a published commitment.** This is a starter for the business +
> counsel. Every uptime figure below is a **bracketed `[N]%` placeholder** — do not publish a number
> the operations posture can't yet back (see "Prerequisites" §6). Reviewed/signed by counsel, it
> becomes Exhibit B to the MSA (`MSA_STARTER.md`).

_Owner: [business + counsel] · Tracks ACTION_TRACKER **W3-3** · Last updated: 2026-06-23_

## 1. Scope
This SLA covers the QUAICU governance Service on the **shared SaaS plane (Model A)** — the Cloud Run
kernel (us-central1) fronted by the Cloudflare Worker, plus the operator console. **Model B**
(customer-hosted single-tenant) uptime is the customer's responsibility on their own infrastructure;
note that distinction in any Model-B order form.

## 2. Uptime commitment (by plan)
| Plan | Monthly Uptime target | Notes |
|------|-----------------------|-------|
| Starter | `[N]%` (e.g. 99.5%) | Best-effort; self-serve support |
| Business | `[N]%` (e.g. 99.9%) | |
| Enterprise | `[N]%` (e.g. 99.95%) | Custom targets negotiable on the order form |

> "Monthly Uptime %" = `(total minutes in month − Downtime minutes) / total minutes in month × 100`.

## 3. Definitions
- **Downtime** — a period in which the governed-action API (`delivery/api/`) returns 5xx / is
  unreachable for requests that pass auth, measured at the edge, excluding the §4 exclusions.
- **Maintenance window** — pre-announced (`[N]` hours' notice), outside which downtime counts.
- **Measurement source** — the external uptime monitor stood up under **W4-1/W4-2** (observability +
  status page). Until that exists, there is no agreed measurement of record — a reason §6 gates
  publishing hard numbers.

## 4. Exclusions (do not count as Downtime)
- Scheduled maintenance announced per §3.
- Faults in **third-party managed services** QUAICU depends on — Google Cloud, Cloudflare,
  Razorpay/Stripe, OpenBao — per `SECURITY.md`'s shared-responsibility boundary. (QUAICU's *misuse*
  of them is not excluded.)
- Customer-caused issues: customer's network, their misconfiguration, their breach of the AUP/MSA,
  or load exceeding contracted rate limits.
- Force majeure.

## 5. Service credits (sole and exclusive remedy)
If the monthly uptime target is missed, the customer may request a credit against a future invoice:

| Monthly Uptime achieved | Service credit (% of that month's fee) |
|-------------------------|----------------------------------------|
| Below target but ≥ `[X]%` | `[5]%` |
| ≥ `[Y]%` and < `[X]%` | `[10]%` |
| < `[Y]%` | `[25]%` |

- Credits are the **sole and exclusive remedy** for missed uptime (align with MSA limitation-of-
  liability, clause 12/13).
- Customer must **request** the credit within `[30]` days of the affected month, with reasonable
  detail. Credits are non-refundable, non-cash, and capped at `[100]%` of the monthly fee.
- For the **Starter** plan (₹10,000/yr), define whether credits apply or it's best-effort only —
  recommended: best-effort, no monetary credit, given the price point.

## 6. Prerequisites before publishing hard numbers ⚠
Do **not** commit contractual uptime until these exist — otherwise the SLA promises what ops can't
measure or recover:
- **W4-1** observability + alerting wired in prod (so Downtime is *detected*).
- **W4-2** public status page (the customer-facing measurement of record).
- **W4-3** a *tested* DR/restore runbook with stated **RTO/RPO**. Cloud SQL PITR exists but the
  restore is **untested** — an untested restore cannot back an RTO claim.
- Decide single-region (us-central1) vs multi-region (W5-2) — single-region caps the achievable
  target and shapes the RTO/RPO you can promise.

## 7. Support response targets
Response/restoration targets live with the support tiers in `ORDER_FORM_AND_PRICING.md` (§Support
tiers) so the order form is the single commercial source of truth; reference them here rather than
duplicating.

## 8. Next actions
1. Operations sets achievable `[N]%` targets once W4-1/2/3 land; counsel reviews credit mechanics.
2. Confirm Starter = best-effort vs credit-bearing.
3. Attach as Exhibit B to the MSA; cross-link the support-tier targets.
