# Data residency & sovereignty

> Where each class of data lives, the egress posture, and the per-region guarantees QUAICU can make.
> Bracketed `[…]` items depend on a deployed region. Backed by the IaC in
> `deploy/terraform/gcp-saas/` (W5-1/W5-2) and the zero-egress method in `ZERO_EGRESS_VALIDATION.md`.

_Owner: [ops + compliance] · Tracks ACTION_TRACKER **W5-4** · Last updated: 2026-06-23_

## Deployment models (residency differs)
- **Model A — shared SaaS plane** (multi-tenant Cloud Run). Residency = the region the stack is
  applied to. One stack **per residency zone** (EU / India / Gulf / US), separate Cloud SQL + secrets.
- **Model B — customer-hosted single-tenant** (`deploy/terraform/gcp-enterprise/`). Data lives entirely
  in the **customer's** GCP project/region; QUAICU never holds it. Strongest residency story.

## Data classes × where they live (per Model-A regional stack)
| Data class | Store | Lives in | Notes |
|------------|-------|----------|-------|
| K·02 audit ledger | Cloud SQL (BUSINESS) / in-mem (STARTER) | the stack's `var.region` | Append-only; STARTER ledger is per-instance ephemeral, audit also flows to Cloud Logging |
| Accounts / API keys | Cloud SQL (`ACCOUNT_DSN`) | the stack's region | Keys stored HMAC-peppered |
| Entitlements / plans | Cloud SQL (`ENTITLEMENTS_DSN`) | the stack's region | |
| Policies | durable policy store | the stack's region | |
| Access logs | Cloud Logging | the project's log region | Configure a regional log bucket for strict residency |
| Payment data | **Razorpay/Stripe (external)** | the processor | QUAICU never stores card data (PCI SAQ-A) |
| Email (OTP/notices) | **Resend (external)** | the processor | Contains email + minimal PII |
| Secrets | Secret Manager | replication policy (set regional for strict residency) | |

> ⚠ **Residency caveats:** Cloud Logging, Secret Manager replication, and the external processors
> (Razorpay/Resend) can place data outside the compute region unless explicitly constrained. For a
> strict regime, pin a **regional log bucket**, **regional Secret Manager replication**, and confirm
> the processors' regional/DPA posture (see `docs/legal/DPA_ART28_STARTER.md`).

## Per-region guarantees
| Zone | Region (preset) | Regime | Posture |
|------|-----------------|--------|---------|
| **EU** | `europe-west1` (`regions/eu.tfvars`) | GDPR | Compute + durable stores in the EEA; enable private egress for no-US-egress; SCCs only if any transfer remains |
| **India** | `asia-south1` (`regions/india.tfvars`) | DPDP (+ RBI/SEBI) | Personal/payment data localized in India; pairs with the RBI/SEBI policy pack's localization rules |
| **Gulf** | `me-central1` (`regions/gulf.tfvars`) | KSA/UAE | In-region compute + storage; verify Cloud SQL + VPC connector availability first |
| **US** | `us-central1` (default) | — | The current live plane |

## How to stand up a new residency zone
1. `cd deploy/terraform/gcp-saas` → `terraform apply -var-file=regions/<zone>.tfvars` (+ secrets).
2. Point the Cloudflare Worker origin (or a region-routing edge) at the new `service_url` output.
3. For strict no-egress, set `enable_private_egress = true` and follow `ZERO_EGRESS_VALIDATION.md`.
4. Pin regional log bucket + Secret Manager replication; confirm processor regions.
5. Record the resulting guarantees back into this matrix for that zone.
