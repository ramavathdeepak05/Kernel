# QUAICU Kernel — Pricing & Tiers (DRAFT)

*[DRAFT for review — confirm prices, quotas, and terms with the team + counsel before publishing.
Numbers below are placeholders aligned to the `TIER_MATRIX` in `core/entitlements/model.py`; that
matrix is the source of truth the kernel enforces, so keep this doc in sync with it.]*

QUAICU is sold in three tiers from one codebase. Limits are enforced fail-closed at the edge
(rate-limit + daily quota) and by per-tier feature gating.

| | **STARTER** (Free) | **BUSINESS** | **ENTERPRISE** |
|---|---|---|---|
| **Price** | $0 | $[TBD]/mo (self-serve) | Custom annual license |
| **Hosting** | Hosted SaaS (you) | Hosted SaaS (you) | Customer-hosted (their cloud) |
| **Governance** | CEL policy engine (in-memory) | CEL engine, durable | Full, durable |
| **Policies** | up to 5 | up to 200 | unbounded |
| **Rate limit** | 60 / min | 600 / min | unbounded |
| **Daily actions** | 10,000 | 1,000,000 | unbounded |
| **Ledger** | in-memory (ephemeral) + log audit | durable Postgres | durable + Cloud KMS (HSM) signing |
| **Inference (AI Gateway)** | — | ✓ | ✓ |
| **HITL approvals** | ✓ (standard profile) | ✓ | ✓ |
| **Consent (DPDP)** | — | ✓ | ✓ |
| **Tenant isolation** | logical (RLS) | logical (RLS) | physical (their deployment) |
| **Regulatory evidence export** | — | ✓ | ✓ + signed packs |
| **Data residency** | our cloud | our cloud | their cloud — we never see data |
| **Support / SLA** | community | standard | enterprise SLA + crypto-review attestation |

## How billing works
- **STARTER → BUSINESS:** self-serve checkout (`POST /v1/billing/checkout` → Stripe/Razorpay); a
  verified webhook flips the tenant's tier in the durable entitlement store. Metered on governed
  actions; an AWS/GCP Marketplace metering path can bill against cloud commit credits.
- **ENTERPRISE:** annual license (offline token gates boot). The customer pays their own cloud infra;
  we charge the license. See `docs/operations/DEPLOYMENT_MODELS.md`.

## Notes
- Upgrades/downgrades take effect on the next request after the webhook lands (idempotent; survive
  restart).
- Quota overrides for specific enterprise contracts are supported per-tenant without a new tier.
- Trial / annual-discount / overage terms: **TBD**.
