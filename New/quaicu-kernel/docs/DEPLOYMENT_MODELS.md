# QUAICU Kernel — Deployment Models (for sales & solution architects)

One codebase, two delivery models. The buyer's **risk appetite and data-residency rules** pick the
model — you don't choose one, you offer both. See also [HOSTING](HOSTING.md),
[GO_LIVE_SETUP](GO_LIVE_SETUP.md), and [ENTERPRISE_CLOUD_STRATEGY](strategy/ENTERPRISE_CLOUD_STRATEGY.md).

---

## Model A — SaaS shared plane (you host)

**You run one deployment; each client is a tenant. They plug in and configure — zero infrastructure.**

- **Who:** mid-market fintechs, Series B+ startups, less-regulated departments.
- **What the client does:** sign up (`POST /v1/signup`) → get a **tenant id + API key** → point their
  app at `https://api.yourco.com/v1/...` (or the SDK at that URL). Configure their own policies
  (`/v1/policies`), models, consent, and tier — all via your API/console, no redeploy.
- **What you run:** `quaicu-kernel-saas` (`delivery/entrypoint_saas.py`) with `TieredKernelProvider`
  routing each request to its tier's kernel; durable Postgres (Cloud SQL/Aurora); the signing backend;
  TLS; scaling. Config: `kernel.saas.toml` → `kernel.starter.toml` + `kernel.business.toml`.
- **Isolation:** by `tenant_id` — per-tenant ledger tables + RLS (F-07). One tenant can never read
  another's actions/ledger/policies.
- **Metering & limits:** automatic at the edge — rate limit (per min), daily quota, feature gating
  from `TIER_MATRIX`, keyed on the verified tenant. Usage counted by `UsageMeter`.
- **Billing:** Stripe/Razorpay (or marketplace metering) → tier flips in the shared `EntitlementStore`.
- **Data flow:** client request → **your VPC** → kernel → (your) inference/signing → response.
- **Margin/pricing:** highest margin; subscription or per-action metering.
- **Tradeoff:** *you process the client's data*. For Tier-1 banks/healthcare this is often a hard no
  (residency/sovereignty). Use Model B for those.

```
 client app ──HTTPS+API key──▶  api.yourco.com (YOUR cloud)
                                 ├─ quaicu-kernel-saas (tier routing)
                                 ├─ Cloud SQL (per-tenant RLS)
                                 └─ KMS / inference (YOUR project)
```

## Model B — Customer-hosted single-tenant (they host)

**The client deploys the kernel into their own cloud account. You never touch their data; you charge a license.**

- **Who:** Tier-1 banks, insurance, healthcare, government.
- **What the client does:** click "Deploy" (marketplace listing → Terraform / Deployment Manager →
  ◻ to author) or run the Docker image / Helm chart in their account. The kernel runs in **their** VPC
  using **their** KMS, inference (Vertex/Bedrock), and Postgres. Config: `kernel.gcp.toml` /
  `kernel.prod.toml`. ENTERPRISE tier boots only with a valid **offline license**
  (`TieredKernelProvider.for_enterprise`).
- **What you run:** nothing in the data path — you issue the license + provide the image/templates.
- **Data flow:** request → **client VPC** → kernel → client's KMS/inference → response. No public
  egress (PSC/PrivateLink); your servers never see their data.
- **Margin/pricing:** high ACV — client pays infra on their cloud commit credits; you charge a license
  fee. Bypasses ~90% of vendor security questionnaires (you don't host their data).
- **Tradeoff:** you don't operate it, so upgrades/support are via the released image + license.

```
 client app ─▶ kernel (CLIENT cloud account, their VPC)
                ├─ Cloud KMS (client) — FIPS 140-2 L3, key never leaves HSM
                ├─ Vertex/Bedrock (client) — private endpoint, no public egress
                └─ Cloud SQL (client)
 you ──issue──▶ offline license token (gates ENTERPRISE boot)
```

---

## At a glance

| | Model A — SaaS (you host) | Model B — Customer-hosted |
|---|---|---|
| Target | mid-market / fintech | regulated (banks, health, gov) |
| Who runs infra | you | the client |
| Who sees the data | you (your VPC) | only the client |
| Entrypoint / config | `quaicu-kernel-saas` / `kernel.saas.toml` | `quaicu-kernel` / `kernel.gcp.toml` + license |
| Tiers served | STARTER, BUSINESS | ENTERPRISE (license-gated) |
| Billing | Stripe/Razorpay/marketplace metering | annual license |
| Tenant isolation | logical (RLS, per-tenant tables) | physical (their own deployment) |
| Margin | highest | high ACV |
| Main objection it answers | "give us something turnkey" | "our data can't leave our cloud" |

**Rule of thumb:** lead with Model A for speed and margin; offer Model B the moment a buyer raises data
residency, sovereignty, or "we self-host everything."
